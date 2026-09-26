# evaluations/views.py — الملف كامل

import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User, UserRole
from accounts.permissions import data_entry_required, school_admin_required
from rules.models import Rule, RuleCategory
from structure.models import Grade, Section, SectionSubject, Subject, Teacher
from students.models import Student

from .forms import EvaluationForm, POSTransactionForm, WeeklySettingsForm
from .models import Evaluation, POSTransaction, WeeklyReset
from .services import POSService


@data_entry_required
def apply_evaluation(request):
    """
    الصفحة الرئيسية لتطبيق التقييم — شل بسيط بس (اختيار فصل + مادة)،
    الجدول نفسه يتحمّل بعدين عبر bulk_table (AJAX) بدون إعادة تحميل الصفحة.
    """
    sections_data = [
        {"id": sec.id, "grade_id": sec.grade_id}
        for sec in Section.objects.all()
    ]
    subjects_data = [
        {"id": s.id, "name": s.name, "grade_ids": list(s.grades.values_list("id", flat=True))}
        for s in Subject.objects.all()
    ]

    week_start = WeeklyReset.current_week_start()
    week_label = (
        f"الأسبوع الحالي — منذ آخر تصفير بتاريخ {week_start:%Y-%m-%d}"
        if week_start else "الأسبوع الحالي — لسا ما صار تصفير أسبوعي (من بداية التسجيل)"
    )

    return render(request, "evaluations/apply_evaluation.html", {
        "sections": Section.objects.select_related("grade"),
        "sections_data": sections_data,
        "subjects_data": subjects_data,
        "week_label": week_label,
    })


@data_entry_required
def bulk_table(request):
    """
    يرجّع جدول الإدخال الجماعي (HTML جاهز، مو JSON) لفصل ونوع تقييم معيّنين
    (وممكن + مادة، لو النوع أكاديمي) — يستدعيها JS صفحة تطبيق التقييم لبناء/تحديث
    الجدول بدون إعادة تحميل الصفحة. القواعد المعروضة كلها من نفس الفئة بالضبط —
    ما فيه خلط بين قواعد أكاديمية وقواعد إشراف بنفس الجدول أبدًا.
    """
    section = get_object_or_404(Section, pk=request.GET.get("section"))
    category = request.GET.get("category")
    if category not in RuleCategory.values:
        raise Http404

    subject = None
    if category == RuleCategory.SUBJECT:
        subject = get_object_or_404(Subject, pk=request.GET.get("subject"))
        rules_qs = Rule.objects.filter(category=RuleCategory.SUBJECT).filter(
            Q(subject__isnull=True) | Q(subject=subject)
        )
    elif category == RuleCategory.REDEMPTION:
        # قواعد استبدال عامة (بلا صفوف محددة) أو مرتبطة بصف هذا الفصل تحديدًا.
        rules_qs = Rule.objects.filter(category=RuleCategory.REDEMPTION).filter(
            Q(grades__isnull=True) | Q(grades=section.grade)
        ).distinct()
    else:
        rules_qs = Rule.objects.filter(category=RuleCategory.GENERAL)

    rules_list = list(rules_qs)

    # فلتر ثانٍ اختياري فوق الجدول: إضافة فقط أو خصم فقط.
    type_filter = request.GET.get("type")
    if type_filter == "add":
        rules_list = [r for r in rules_list if not r.is_deduction]
    elif type_filter == "deduct":
        rules_list = [r for r in rules_list if r.is_deduction]

    # ترتيب: كل أعمدة الإضافة أولاً ثم كل أعمدة الخصم — وتعليم أول عمود خصم
    # بعلامة "بداية مجموعة" عشان القالب يرسم الفاصل البصري بينهم، لكن فقط
    # لما تكون المجموعتان ظاهرتين معًا (فلتر "الكل") — لا داعي للفاصل لما
    # يكون الجدول خصمًا بحتًا أو إضافة بحتة.
    rules = sorted(rules_list, key=lambda r: (r.is_deduction, r.name))
    seen_add = False
    seen_deduct = False
    for rule in rules:
        rule.divider_before = rule.is_deduction and seen_add and not seen_deduct
        seen_deduct = seen_deduct or rule.is_deduction
        seen_add = seen_add or not rule.is_deduction

    students = list(Student.objects.filter(section=section, is_active=True).order_by("full_name"))

    week_start = WeeklyReset.current_week_start()
    evaluations = Evaluation.objects.filter(student__in=students, rule__in=rules)
    evaluations = evaluations.filter(subject=subject) if subject else evaluations.filter(subject__isnull=True)
    if week_start:
        evaluations = evaluations.filter(created_at__gte=week_start)

    applied_map = {(ev.student_id, ev.rule_id): ev.value for ev in evaluations}

    rows = []
    for student in students:
        cells = [
            {"rule": rule, "value": applied_map.get((student.id, rule.id)), "divider_before": rule.divider_before}
            for rule in rules
        ]
        balance = (
            Evaluation.weekly_total(student, subject=subject)
            if subject else Evaluation.weekly_total(student, category=category)
        )
        rows.append({"student": student, "cells": cells, "balance": balance})

    return render(request, "evaluations/_bulk_table.html", {
        "section": section,
        "subject": subject,
        "category": category,
        "rules": rules,
        "rows": rows,
    })


def _get_applied_subject(request, rule):
    if rule.category == RuleCategory.SUBJECT:
        return get_object_or_404(Subject, pk=request.POST.get("subject"))
    return None


def _existing_evaluation(student, rule, applied_subject, week_start):
    qs = Evaluation.objects.filter(student=student, rule=rule)
    qs = qs.filter(subject=applied_subject) if applied_subject else qs.filter(subject__isnull=True)
    if week_start:
        qs = qs.filter(created_at__gte=week_start)
    return qs.first()


def _toggle_one(student, rule, applied_subject, raw_value, user, week_start):
    """
    منطق ضغطة وحدة على خلية (تطبيق/إلغاء/استبدال) — تُستخدم من bulk_toggle
    مباشرة، وتُشكّل أساس الفرق مع _apply_one (التطبيق الجماعي القسري بالأسفل).
    ترجّع dict فيه ok/applied/value/previous_value أو ok/error.
    """
    existing = _existing_evaluation(student, rule, applied_subject, week_start)
    previous_value = existing.value if existing else None

    if rule.is_range:
        try:
            requested_value = int(raw_value)
        except (TypeError, ValueError):
            return {"ok": False, "error": "قيمة غير صحيحة"}

        if existing and existing.value == requested_value:
            existing.delete()
            return {"ok": True, "applied": False, "value": None, "previous_value": previous_value}

        try:
            _replace_existing(existing, student, rule, applied_subject, requested_value, user)
        except _ToggleError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "applied": True, "value": requested_value, "previous_value": previous_value}

    if existing:
        existing.delete()
        return {"ok": True, "applied": False, "value": None, "previous_value": previous_value}

    form = EvaluationForm(data={
        "student": student.id, "rule": rule.id,
        "subject": applied_subject.id if applied_subject else "",
        "value": "",
    }, recorded_by=user)
    if not form.is_valid():
        return {"ok": False, "error": _first_error(form)}
    form.save()
    return {"ok": True, "applied": True, "value": rule.value, "previous_value": previous_value}


def _apply_one(student, rule, applied_subject, value, user, week_start):
    """
    "تطبيق قسري" (Set) بدل toggle — تستخدمها bulk_apply_many عشان نتيجة التطبيق
    الجماعي تكون متوقعة دايمًا (كل الطلاب المحدّدين ينتهي بهم القاعدة مطبّقة
    بنفس القيمة)، بغض النظر عن حالة كل طالب قبل الضغط على "تطبيق".
    """
    existing = _existing_evaluation(student, rule, applied_subject, week_start)
    previous_value = existing.value if existing else None
    try:
        _replace_existing(existing, student, rule, applied_subject, value, user)
    except _ToggleError as exc:
        return {"ok": False, "error": str(exc), "previous_value": previous_value}
    return {"ok": True, "value": value, "previous_value": previous_value}


@require_POST
@data_entry_required
def bulk_toggle(request):
    """
    ضغطة وحدة على خلية بجدول الإدخال الجماعي:
    - القاعدة مو مطبّقة لهذا الطالب هذا الأسبوع → تُطبّق (تُسجَّل).
    - مطبّقة بنفس القيمة (أو قاعدة ثابتة مطبّقة أصلاً) → تُلغى (تُحذف).
    - مطبّقة بقيمة مختلفة (قاعدة مدى) → تُستبدل بالقيمة الجديدة.
    """
    student = get_object_or_404(Student, pk=request.POST.get("student"), is_active=True)
    rule = get_object_or_404(Rule, pk=request.POST.get("rule"))
    applied_subject = _get_applied_subject(request, rule)
    week_start = WeeklyReset.current_week_start()

    outcome = _toggle_one(student, rule, applied_subject, request.POST.get("value"), request.user, week_start)
    if not outcome["ok"]:
        return JsonResponse({"ok": False, "error": outcome["error"]}, status=400)

    balance = (
        Evaluation.weekly_total(student, subject=applied_subject)
        if applied_subject else Evaluation.weekly_total(student, category=rule.category)
    )
    return JsonResponse({
        "ok": True,
        "applied": outcome["applied"],
        "value": outcome["value"],
        "previous_value": outcome["previous_value"],
        "balance": balance,
        "undo": [{
            "student": student.id, "rule": rule.id,
            "subject": applied_subject.id if applied_subject else None,
            "previous_value": outcome["previous_value"],
        }],
    })


@require_POST
@data_entry_required
def bulk_apply_many(request):
    """
    تطبيق قاعدة واحدة (بقيمة واحدة) على مجموعة طلاب محدّدين دفعة وحدة —
    تدعم "التحديد المتعدد" أعلى الجدول. كل طالب يُعامل بشكل مستقل بمنطق Set
    قسري (_apply_one)، فيرجع نفس النتيجة دايمًا بغض النظر عن حالته الحالية.
    فشل طالب واحد (مثلاً تجاوز سقفه الأسبوعي) ما يوقف تطبيق البقية.
    """
    rule = get_object_or_404(Rule, pk=request.POST.get("rule"))
    student_ids = request.POST.getlist("students")
    if not student_ids:
        return JsonResponse({"ok": False, "error": "لا يوجد طلاب محدّدين"}, status=400)

    applied_subject = _get_applied_subject(request, rule)

    if rule.is_range:
        try:
            value = int(request.POST.get("value"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "قيمة غير صحيحة"}, status=400)
        if value not in rule.range_values:
            return JsonResponse({"ok": False, "error": "القيمة خارج المدى المسموح لهذه القاعدة"}, status=400)
    else:
        value = rule.value

    students = list(Student.objects.filter(id__in=student_ids, is_active=True))
    week_start = WeeklyReset.current_week_start()

    results = []
    undo_items = []
    success_count = 0
    for student in students:
        outcome = _apply_one(student, rule, applied_subject, value, request.user, week_start)
        results.append({
            "student": student.id,
            "ok": outcome["ok"],
            "error": outcome.get("error"),
        })
        if outcome["ok"]:
            success_count += 1
            undo_items.append({
                "student": student.id,
                "rule": rule.id,
                "subject": applied_subject.id if applied_subject else None,
                "previous_value": outcome["previous_value"],
            })

    return JsonResponse({
        "ok": True,
        "success_count": success_count,
        "total": len(students),
        "results": results,
        "undo": undo_items,
    })


@require_POST
@data_entry_required
def bulk_restore(request):
    """
    تراجع (Undo) — يرجّع كل عنصر بالضبط لقيمته قبل آخر عملية (فردية أو جماعية)،
    بدون إعادة فحص السقف الأسبوعي: هذي استعادة لحالة كانت صحيحة أصلاً وقت
    تسجيلها، مو تسجيل تقييم جديد. الواجهة تعيد تحميل الجدول بعدها للمزامنة.
    """
    try:
        items = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "بيانات غير صحيحة"}, status=400)
    if not isinstance(items, list):
        return JsonResponse({"ok": False, "error": "بيانات غير صحيحة"}, status=400)

    week_start = WeeklyReset.current_week_start()

    with transaction.atomic():
        for item in items:
            student = get_object_or_404(Student, pk=item.get("student"))
            rule = get_object_or_404(Rule, pk=item.get("rule"))
            subject_id = item.get("subject")
            applied_subject = get_object_or_404(Subject, pk=subject_id) if subject_id else None
            previous_value = item.get("previous_value")

            existing = _existing_evaluation(student, rule, applied_subject, week_start)

            if previous_value is None:
                if existing:
                    existing.delete()
            elif existing:
                existing.value = previous_value
                existing.save(update_fields=["value"])
            else:
                Evaluation.objects.create(
                    student=student, rule=rule, subject=applied_subject,
                    value=previous_value, recorded_by=request.user,
                )

    return JsonResponse({"ok": True})


def _first_error(form):
    for errors in form.errors.values():
        return errors[0]
    return "تعذّر تسجيل التقييم"


class _ToggleError(Exception):
    pass


def _replace_existing(existing, student, rule, applied_subject, requested_value, user):
    """
    تستبدل قيمة قاعدة بقيمة جديدة داخل transaction — لو القيمة الجديدة رفضت
    (مثلاً تجاوز السقف الأسبوعي)، التراجع يشمل حذف القديمة كمان، عشان ما تضيع
    قيمة الطالب الحالية لو الاستبدال فشل.
    """
    with transaction.atomic():
        if existing:
            existing.delete()
        form = EvaluationForm(data={
            "student": student.id, "rule": rule.id,
            "subject": applied_subject.id if applied_subject else "",
            "value": requested_value,
        }, recorded_by=user)
        if not form.is_valid():
            raise _ToggleError(_first_error(form))
        form.save()


@school_admin_required
def activity_log(request):
    """
    سجل نشاط موحّد يجمع نوعين من الأحداث مختلفَي البنية: تقييمات
    (Evaluation) وعمليات تحويل (POSTransaction) — كل نوع من جدول مختلف
    تمامًا (لا علاقة FK مباشرة بينهما)، فما فيه طريقة نجمعهما باستعلام
    واحد. نجلب كل نوع بفلاتره المناسبة على حدة (فلاتر المادة/القاعدة/
    المعلّمة ما تنطبق على التحويلات أصلاً فتُستبعد من نتائجها)، نعلّم كل
    عنصر بنوعه (activity_kind) للقالب، ثم ندمجهما مرتّبين زمنيًا بلغة
    Python (المقياس هنا صغير — سقف 200 عنصر لكل نوع أصلاً — فالدمج
    بالذاكرة أبسط وأوضح من محاولة UNION على جدولين مختلفَي الأعمدة).
    """
    evaluations = Evaluation.objects.select_related(
        "student", "student__section", "student__section__grade",
        "rule", "subject", "recorded_by",
    )
    transfers = POSTransaction.objects.select_related(
        "seller", "seller__section", "buyer", "buyer__section", "recorded_by",
    )

    staff_id = request.GET.get("staff")
    if staff_id:
        evaluations = evaluations.filter(recorded_by_id=staff_id)
        transfers = transfers.filter(recorded_by_id=staff_id)

    student_id = request.GET.get("student")
    selected_student = None
    if student_id:
        selected_student = get_object_or_404(Student, pk=student_id)
        evaluations = evaluations.filter(student=selected_student)
        transfers = transfers.filter(Q(seller=selected_student) | Q(buyer=selected_student))

    teacher_id = request.GET.get("teacher")
    selected_teacher = None
    if teacher_id:
        selected_teacher = get_object_or_404(Teacher, pk=teacher_id)
        # المعلّمة مو مرتبطة مباشرة بالتقييم — بس بربطها بـ(الفصل، المادة)
        # اللي تدرّسها فعليًا عبر SectionSubject، فنبني شرط OR على كل زوج
        # (فصل، مادة) تدرّسه هذه المعلّمة.
        taught_pairs = list(
            SectionSubject.objects.filter(teacher=selected_teacher)
            .values_list("section_id", "subject_id")
        )
        if taught_pairs:
            pairs_query = Q()
            for index, (pair_section_id, pair_subject_id) in enumerate(taught_pairs):
                pair_q = Q(student__section_id=pair_section_id, subject_id=pair_subject_id)
                pairs_query = pair_q if index == 0 else pairs_query | pair_q
            evaluations = evaluations.filter(pairs_query)
        else:
            evaluations = evaluations.none()
        # التحويلات مو مرتبطة بمادة ولا معلّمة أصلاً — تُستبعد كليًا لو
        # الفلترة بمعلّمة معيّنة (فلترة غير منطقية لعمليات ما فيها مادة).
        transfers = transfers.none()

    grade_id = request.GET.get("grade")
    if grade_id:
        evaluations = evaluations.filter(student__section__grade_id=grade_id)
        transfers = transfers.filter(
            Q(seller__section__grade_id=grade_id) | Q(buyer__section__grade_id=grade_id)
        )

    section_id = request.GET.get("section")
    if section_id:
        evaluations = evaluations.filter(student__section_id=section_id)
        transfers = transfers.filter(
            Q(seller__section_id=section_id) | Q(buyer__section_id=section_id)
        )

    subject_id = request.GET.get("subject")
    if subject_id:
        evaluations = evaluations.filter(subject_id=subject_id)
        transfers = transfers.none()  # لا مادة للتحويلات أصلاً

    rule_id = request.GET.get("rule")
    if rule_id:
        evaluations = evaluations.filter(rule_id=rule_id)
        transfers = transfers.none()  # لا قاعدة للتحويلات أصلاً

    eval_type = request.GET.get("type")
    if eval_type == "add":
        evaluations = evaluations.filter(value__gt=0)
        transfers = transfers.none()
    elif eval_type == "deduct":
        evaluations = evaluations.filter(value__lt=0)
        transfers = transfers.none()
    elif eval_type == "transfer":
        evaluations = evaluations.none()

    date_from = request.GET.get("date_from")
    if date_from:
        evaluations = evaluations.filter(created_at__date__gte=date_from)
        transfers = transfers.filter(created_at__date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        evaluations = evaluations.filter(created_at__date__lte=date_to)
        transfers = transfers.filter(created_at__date__lte=date_to)

    evaluations_list = list(evaluations[:200])
    for entry in evaluations_list:
        entry.activity_kind = "evaluation"

    transfers_list = list(transfers[:200])
    for tx in transfers_list:
        tx.activity_kind = "transfer"

    activity_items = sorted(
        evaluations_list + transfers_list, key=lambda item: item.created_at, reverse=True
    )[:200]

    return render(request, "evaluations/activity_log.html", {
        "activity_items": activity_items,
        "staff_list": User.objects.filter(role=UserRole.DATA_ENTRY),
        "grade_list": Grade.objects.all(),
        "section_list": Section.objects.select_related("grade"),
        "subject_list": Subject.objects.all(),
        "rules_list": Rule.objects.all().order_by("name"),
        "selected_staff_id": staff_id,
        "selected_student": selected_student,
        "selected_teacher": selected_teacher,
        "selected_grade_id": grade_id,
        "selected_section_id": section_id,
        "selected_subject_id": subject_id,
        "selected_rule_id": rule_id,
        "selected_type": eval_type,
        "date_from": date_from,
        "date_to": date_to,
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


@data_entry_required
def pos_manage(request):
    """
    شاشة "تاجر التبيان" — تحويل رصيد تراكمي بين طرفين (طالب أو طالبة)،
    لموظفة الإدخال. الفحص الودود المبكر بـ POSTransactionForm.clean()،
    والتنفيذ الفعلي الآمن (ذري + مقفول ضد race conditions) عبر
    POSService.transfer.

    الواجهة تعتمد فلترة متسلسلة (الصف ثم الفصل) ثم بحث مباشر (autocomplete)
    لاختيار طرفَي التحويل من طلاب الفصل المختار فقط — لذا هذا الـ view يمرر
    كل بيانات الصفوف/الفصول/الطلاب النشطين دفعة واحدة كـ JSON (بنفس أسلوب
    sections_data/subjects_data بصفحة apply_evaluation)، والفلترة الفعلية
    تصير بالكامل عبر JS بالمتصفح بدون أي طلبات AJAX إضافية.
    """
    if request.method == "POST":
        form = POSTransactionForm(request.POST)
        if form.is_valid():
            try:
                POSService.transfer(
                    buyer_id=form.cleaned_data["buyer"].id,
                    seller_id=form.cleaned_data["seller"].id,
                    amount=form.cleaned_data["amount"],
                    recorded_by=request.user,
                )
                messages.success(request, "تم تسجيل التحويل بنجاح")
                return redirect("evaluations:pos_manage")
            except ValidationError as e:
                form.add_error(None, e)
    else:
        form = POSTransactionForm()

    students = (
        Student.objects.filter(is_active=True)
        .select_related("section")
        .order_by("full_name")
    )
    students_data = [
        {
            "id": s.id,
            "name": s.full_name,
            "section_id": s.section_id,
            "balance": Evaluation.cumulative_total(s),
        }
        for s in students
    ]

    sections_data = [
        {
            "id": section.id,
            "grade_id": section.grade_id,
            "label": f"{section.name} ({section.get_gender_display()})",
        }
        for section in Section.objects.select_related("grade")
    ]

    recent_transactions = (
        POSTransaction.objects.select_related("buyer", "seller", "recorded_by")
        .order_by("-created_at")[:30]
    )

    return render(request, "evaluations/pos_manage.html", {
        "form": form,
        "grades": Grade.objects.all(),
        "students_data": students_data,
        "sections_data": sections_data,
        "transactions": recent_transactions,
    })
