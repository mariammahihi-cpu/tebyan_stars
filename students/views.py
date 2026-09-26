import json

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.permissions import school_admin_required
from evaluations.models import Evaluation
from rules.models import RuleCategory
from structure.models import Section, SectionSubject


from .models import Student


def _generate_student_number(section):
    base = f"{section.grade.number}-{section.name}"
    n = Student.objects.filter(section=section).count() + 1
    candidate = f"{base}-{n}"
    while Student.objects.filter(student_number=candidate).exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@school_admin_required
def classroom_roster(request, section_id):
    section = get_object_or_404(Section, pk=section_id)

    students = Student.objects.filter(section=section)

    search_q = request.GET.get("q", "").strip()
    if search_q:
        students = students.filter(
            Q(full_name__icontains=search_q) | Q(student_number__icontains=search_q)
        )

    sort = request.GET.get("sort", "name")
    if sort in ("points_desc", "points_asc"):
        # الرصيد محسوب ديناميكيًا (evaluations)، مو حقل بقاعدة البيانات —
        # نرتب يدويًا بعد ما نحسب القيم، مو عبر order_by مباشر
        students_list = list(students)
        students_list.sort(
            key=lambda s: Evaluation.cumulative_total(s),
            reverse=(sort == "points_desc"),
        )
    else:
        students_list = list(students.order_by("full_name"))

    students_data = [
        {
            "student": s,
            "cumulative_subjects": Evaluation.cumulative_total(s, category=RuleCategory.SUBJECT),
            "cumulative_supervision": Evaluation.cumulative_total(s, category=RuleCategory.GENERAL),
            "weekly_subjects": Evaluation.weekly_total(s, category=RuleCategory.SUBJECT),
            "weekly_supervision": Evaluation.weekly_total(s, category=RuleCategory.GENERAL),
        }
        for s in students_list
    ]

    return render(request, "students/classroom_roster.html", {
        "section": section,
        "students_data": students_data,
        "search_q": search_q,
        "sort": sort,
    })


@school_admin_required
def student_detail(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    section = student.section

    subject_rows = [
        {
            "subject": section_subject.subject,
            "weekly": Evaluation.weekly_total(student, subject=section_subject.subject),
            "cumulative": Evaluation.cumulative_total(student, subject=section_subject.subject),
        }
        for section_subject in SectionSubject.objects.filter(section=section)
            .select_related("subject").order_by("subject__name")
    ]

    return render(request, "students/student_detail.html", {
        "student": student,
        "section": section,
        "subject_rows": subject_rows,
        "cumulative_subjects": Evaluation.cumulative_total(student, category=RuleCategory.SUBJECT),
        "cumulative_supervision": Evaluation.cumulative_total(student, category=RuleCategory.GENERAL),
        "weekly_subjects": Evaluation.weekly_total(student, category=RuleCategory.SUBJECT),
        "weekly_supervision": Evaluation.weekly_total(student, category=RuleCategory.GENERAL),
    })


@school_admin_required
@require_POST
def quick_add_student(request, section_id):
    section = get_object_or_404(Section, pk=section_id)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"ok": False, "error": "بيانات غير صحيحة"}, status=400)

    full_name = (payload.get("full_name") or "").strip()
    if not full_name:
        return JsonResponse({"ok": False, "error": "يجب إدخال اسم الطالب"}, status=400)

    student = Student.objects.create(
        full_name=full_name,
        student_number=_generate_student_number(section),
        section=section,
    )

    return JsonResponse({
        "ok": True,
        "student": {
            "id": student.id,
            "full_name": student.full_name,
            "student_number": student.student_number,
        },
    })


@school_admin_required
@require_POST
def edit_student_ajax(request, student_id):
    student = get_object_or_404(Student, pk=student_id)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"ok": False, "error": "بيانات غير صحيحة"}, status=400)

    full_name = (payload.get("full_name") or "").strip()
    student_number = (payload.get("student_number") or "").strip()

    if not full_name or not student_number:
        return JsonResponse({"ok": False, "error": "الاسم ورقم القيد مطلوبين"}, status=400)

    if Student.objects.exclude(pk=student.pk).filter(student_number=student_number).exists():
        return JsonResponse({"ok": False, "error": "رقم القيد هذا مستخدم من قبل"}, status=400)

    student.full_name = full_name
    student.student_number = student_number
    student.save()

    return JsonResponse({"ok": True, "full_name": student.full_name, "student_number": student.student_number})


@school_admin_required
@require_POST
def toggle_student_active_ajax(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    student.is_active = not student.is_active
    student.save()
    return JsonResponse({"ok": True, "is_active": student.is_active})