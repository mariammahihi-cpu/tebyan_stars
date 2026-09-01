# evaluations/views.py — الملف كامل

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User, UserRole
from accounts.permissions import data_entry_required, school_admin_required
from rules.models import Rule, RuleCategory
from structure.models import Grade, Subject
from students.models import Student

from .forms import EvaluationForm, WeeklySettingsForm
from .models import Evaluation, WeeklyReset


@data_entry_required
def apply_evaluation(request):
    if request.method == "POST":
        form = EvaluationForm(request.POST, recorded_by=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تسجيل التقييم بنجاح")
            return redirect("evaluations:apply_evaluation")
    else:
        form = EvaluationForm(recorded_by=request.user)

    subjects_data = [
        {"id": s.id, "grade_ids": list(s.grades.values_list("id", flat=True))}
        for s in Subject.objects.all()
    ]
    rules_data = [
        {"id": r.id, "category": r.category, "subject_id": r.subject_id}
        for r in Rule.objects.all()
    ]
    students_data = [
        {"id": st.id, "grade_id": st.section.grade_id}
        for st in Student.objects.filter(is_active=True).select_related("section")
    ]

    return render(request, "evaluations/apply_evaluation.html", {
        "form": form,
        "grades": Grade.objects.all(),
        "subjects_data": subjects_data,
        "rules_data": rules_data,
        "students_data": students_data,
    })


@data_entry_required
def student_balance(request, student_id):
    """يرجّع رصيد طالب معيّن كـ JSON — يستدعيها JavaScript صفحة تطبيق التقييم لحظيًا."""
    student = get_object_or_404(Student, pk=student_id, is_active=True)
    subject_id = request.GET.get("subject")

    weekly_subject = None
    if subject_id:
        subject = get_object_or_404(Subject, pk=subject_id)
        weekly_subject = Evaluation.weekly_total(student, subject=subject)

    return JsonResponse({
        "weekly_subject": weekly_subject,
        "weekly_supervision": Evaluation.weekly_total(student, category=RuleCategory.GENERAL),
        "cumulative": Evaluation.cumulative_total(student),
    })


@school_admin_required
def activity_log(request):
    evaluations = Evaluation.objects.select_related(
        "student", "rule", "subject", "recorded_by"
    )

    staff_id = request.GET.get("staff")
    if staff_id:
        evaluations = evaluations.filter(recorded_by_id=staff_id)

    return render(request, "evaluations/activity_log.html", {
        "evaluations": evaluations[:200],
        "staff_list": User.objects.filter(role=UserRole.DATA_ENTRY),
        "selected_staff_id": staff_id,
    })


@school_admin_required
def weekly_settings(request):
    if request.method == "POST":
        form = WeeklySettingsForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث الإعدادات بنجاح")
            return redirect("evaluations:weekly_settings")
    else:
        form = WeeklySettingsForm()

    return render(request, "evaluations/weekly_settings.html", {"form": form})


@require_POST
@school_admin_required
def weekly_reset(request):
    WeeklyReset.objects.create(performed_by=request.user)
    messages.success(request, "تم تصفير الرصيد الأسبوعي لجميع الطلاب بنجاح")
    return redirect("evaluations:weekly_settings")