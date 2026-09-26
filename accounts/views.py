from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.db.models import Q

from analytics.services import compute_dashboard_analytics
from evaluations.models import Evaluation, WeeklyReset
from structure.models import Section, SectionSubject, Subject, Teacher
from students.models import Student

from .forms import CreateAccountForm, LoginForm
from .models import User, UserRole
from .permissions import (
    data_entry_required,
    required_role,
    school_admin_required,
    super_admin_required,
)

def _dashboard_url_name(user):
    """يرجّع اسم مسار (URL name) لوحة التحكم المناسبة لدور المستخدم."""
    if user.role == UserRole.SUPER_ADMIN:
        return "accounts:super_admin_dashboard"
    if user.role == UserRole.SCHOOL_ADMIN:
        return "accounts:school_admin_dashboard"
    return "accounts:data_entry_dashboard"


def login_view(request):
    # إذا مسجلة دخول أصلاً، ما فيه داعي تشوف فورم تسجيل الدخول من جديد
    if request.user.is_authenticated:
        return redirect(_dashboard_url_name(request.user))

    if request.method == "POST":
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)

            # لو المستخدمة كانت رايحة لصفحة محمية معينة وتم رجّعها لتسجيل
            # الدخول (عبر required_role بملف permissions.py)، بعد نجاح
            # الدخول نرجّعها لنفس الصفحة اللي كانت طالباها، مو للوحة العامة.
            next_url = request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect(_dashboard_url_name(user))
    else:
        form = LoginForm(request=request)

    return render(request, "accounts/login.html", {
        "form": form,
        "next": request.POST.get("next", request.GET.get("next", "")),
    })


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("accounts:login")


@super_admin_required
def super_admin_dashboard(request):
    """
    الصفحة الرئيسية لمسؤولة النظام — ملخص إحصائي سريع (عدد الطلاب/المعلّمات/
    الفصول، وصافي نجوم الأسبوع الحالي)، بالإضافة للوحة تحليلات المدرسة
    الكاملة نفسها المستخدمة بلوحة مديرة المدرسة (نفس compute_dashboard_analytics
    ونفس القالب الجزئي، بدون أي تكرار لمنطق الاستعلامات أو الواجهة).
    """
    weekly_totals = Evaluation.weekly_school_totals()

    context = {
        "students_count": Student.objects.filter(is_active=True).count(),
        "teachers_count": Teacher.objects.count(),
        "sections_count": Section.objects.count(),
        "weekly_add": weekly_totals["add"],
        "weekly_deduct": weekly_totals["deduct"],
        "weekly_net": weekly_totals["net"],
    }
    context.update(compute_dashboard_analytics())

    return render(request, "accounts/super_admin_dashboard.html", context)


@school_admin_required
def school_admin_dashboard(request):
    """
    الصفحة الرئيسية لمديرة المدرسة — نظرة إشرافية عامة على مستوى المدرسة كاملة
    (مو تنفيذية زي لوحة موظفة الإدخال): نسبة الإنجاز الأسبوعي على مستوى كل
    الفصول والمواد مجتمعة، عدد الطلاب المُقيّمين، تنبيه للفصول عديمة النشاط،
    واختصارات لأكثر إجراءاتها استخدامًا. بدون أي تحليلات تفصيلية — تلك مؤجّلة.
    """
    sections = list(Section.objects.select_related("grade").all())
    applicable_pairs = set(SectionSubject.objects.values_list("section_id", "subject_id"))

    week_start = WeeklyReset.current_week_start()
    week_evaluations = Evaluation.objects.all()
    if week_start:
        week_evaluations = week_evaluations.filter(created_at__gte=week_start)

    covered_pairs = set(
        week_evaluations.filter(subject__isnull=False)
        .values_list("student__section_id", "subject_id")
        .distinct()
    ) & applicable_pairs

    total_pairs = len(applicable_pairs)
    done_pairs = len(covered_pairs)
    progress_percent = round(100 * done_pairs / total_pairs) if total_pairs else 0

    students_evaluated_count = week_evaluations.values("student_id").distinct().count()

    # فصول ما فيها ولا تقييم واحد هذا الأسبوع (بأي مادة أو إشراف) — تنبيه بسيط،
    # بدون أي شرط "قرب نهاية الأسبوع" لأن التصفير يدوي بالكامل حاليًا وما فيه
    # طول أسبوع ثابت محفوظ بالنظام نقدر نقيس عليه "قرب الانتهاء".
    touched_section_ids = set(week_evaluations.values_list("student__section_id", flat=True).distinct())
    zero_activity_sections = [s for s in sections if s.id not in touched_section_ids]

    week_label = (
        f"بداية الأسبوع الحالي: {week_start:%Y-%m-%d}"
        if week_start else "لسا ما صار تصفير أسبوعي — الأسبوع الحالي من بداية التسجيل"
    )

    return render(request, "accounts/school_admin_dashboard.html", {
        "total_pairs": total_pairs,
        "done_pairs": done_pairs,
        "progress_percent": progress_percent,
        "students_evaluated_count": students_evaluated_count,
        "zero_activity_sections": zero_activity_sections,
        "week_start": week_start,
        "week_label": week_label,
    })


@data_entry_required
def data_entry_dashboard(request):
    """
    الصفحة الرئيسية لموظفة الإدخال — نظرة سريعة على تغطية الأسبوع الحالي بس
    ("وين وصلت، وشنو باقي")، بدون أي تحليلات إضافية (تلك من اختصاص لوحة المديرة).
    الترتيب: ملخص مضغوط أولاً، بعده الفصول المحتاجة إدخال، والخريطة التفصيلية
    آخر شي (مطوية افتراضيًا) — عشان أهم معلومة تكون أول شي تشوفه بدون سكرول.
    كل الحسابات مبنية على استعلامات مجمّعة قليلة (Set لكل جانب)، مو استعلام
    لكل خلية بالشبكة — عشان الصفحة تبقى خفيفة حتى لو المدرسة كبرت.
    """
    sections = list(Section.objects.select_related("grade").all())
    subjects = list(Subject.objects.all())

    # أي (فصل، مادة) فعليًا مُسندة لمعلّمة — هذا اللي يحدد الخلايا "المنطبقة"
    # بالشبكة والمقام لنسبة الإنجاز، أدق من الاعتماد بس على ربط المادة بالصف العام.
    applicable_pairs = set(SectionSubject.objects.values_list("section_id", "subject_id"))

    week_start = WeeklyReset.current_week_start()
    week_evaluations = Evaluation.objects.all()
    if week_start:
        week_evaluations = week_evaluations.filter(created_at__gte=week_start)

    # استعلام وحد يرجّع كل أزواج (فصل، مادة) اللي فيها تقييم مسجّل هذا الأسبوع —
    # بدل ما نسأل عن كل خلية لحالها. نتقاطع مع applicable_pairs عشان الملخص
    # والنسب تبقى متسقة حتى لو انسجل تقييم قبل ما تنضاف SectionSubject رسميًا.
    covered_pairs = set(
        week_evaluations.filter(subject__isnull=False)
        .values_list("student__section_id", "subject_id")
        .distinct()
    ) & applicable_pairs

    total_pairs = len(applicable_pairs)
    done_pairs = len(covered_pairs)
    progress_percent = round(100 * done_pairs / total_pairs) if total_pairs else 0

    grid_rows = []
    needs_entry = []
    for section in sections:
        cells = []
        section_applicable = 0
        section_covered = 0
        for subject in subjects:
            pair = (section.id, subject.id)
            applicable = pair in applicable_pairs
            covered = pair in covered_pairs
            if applicable:
                section_applicable += 1
                if covered:
                    section_covered += 1
            cells.append({"subject": subject, "applicable": applicable, "covered": covered})
        grid_rows.append({"section": section, "cells": cells})

        # "محتاجة إدخال" = أقل من نصف موادها المنطبقة مُقيّمة هذا الأسبوع
        # (مو بس صفر تقييمات) — الفصول اللي ما فيها ولا مادة مُسندة أصلاً
        # (section_applicable == 0) نستثنيها، لأنها مشكلة إعداد مو نقص إدخال.
        if section_applicable and section_covered < section_applicable / 2:
            # درجة الإلحاح لتلوين البطاقة: صفر أو مادة وحدة مُقيّمة = خطر،
            # وإلا لحد نص الإجمالي = تحذير متوسط، وفوق النص = محايد (نظريًا
            # ما تصير هون لأن الفلترة فوق أصلاً تستثني نصف الإجمالي فأكثر،
            # لكن نحسبها بشكل صحيح احتياطًا لو تغيّر حد الفلترة مستقبلًا).
            if section_covered <= 1:
                severity = "danger"
            elif section_covered <= section_applicable / 2:
                severity = "warning"
            else:
                severity = "neutral"

            needs_entry.append({
                "section": section,
                "covered": section_covered,
                "total": section_applicable,
                "severity": severity,
            })

    needs_entry.sort(key=lambda item: item["covered"] / item["total"])

    week_label = (
        f"بداية الأسبوع الحالي: {week_start:%Y-%m-%d}"
        if week_start else "لسا ما صار تصفير أسبوعي — الأسبوع الحالي من بداية التسجيل"
    )

    return render(request, "accounts/data_entry_dashboard.html", {
        "subjects": subjects,
        "grid_rows": grid_rows,
        "needs_entry": needs_entry,
        "week_label": week_label,
        "total_pairs": total_pairs,
        "done_pairs": done_pairs,
        "progress_percent": progress_percent,
    })

@super_admin_required
def account_list(request):
    """قائمة كل الحسابات ما عدا حسابات Super Admin (مالهاش داعي تدار من هون)."""
    accounts = User.objects.exclude(role=UserRole.SUPER_ADMIN).order_by("role", "full_name")
    return render(request, "accounts/account_list.html", {"accounts": accounts})


@super_admin_required
def create_account(request):
    if request.method == "POST":
        form = CreateAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(request, f"تم إنشاء حساب {account.full_name} بنجاح")
            return redirect("accounts:account_list")
    else:
        form = CreateAccountForm()

    return render(request, "accounts/create_account.html", {"form": form})


@school_admin_required
def data_entry_account_list(request):
    """قائمة موظفات الإدخال بس — هاي شاشة School Admin اليومية لتفعيل/تعطيل الحسابات."""
    accounts = User.objects.filter(role=UserRole.DATA_ENTRY).order_by("full_name")
    return render(request, "accounts/data_entry_account_list.html", {"accounts": accounts})


@require_POST
@required_role(UserRole.SCHOOL_ADMIN)
def toggle_account_active(request, user_id):
    """
    تبديل حالة تفعيل حساب. Super Admin بتوصلها تلقائيًا (معفاة من فحص الدور
    بـ required_role)، وSchool Admin بتوصلها بس — لكن مقيّدة هون داخل الجسم
    بقاعدة عمل: ما تقدر تلمس إلا حسابات Data Entry.
    """
    target = get_object_or_404(User, pk=user_id)

    if request.user.role == UserRole.SCHOOL_ADMIN and target.role != UserRole.DATA_ENTRY:
        raise PermissionDenied("يمكنك تفعيل أو تعطيل حسابات موظفات الإدخال فقط")

    if target.pk == request.user.pk:
        raise PermissionDenied("لا يمكنك تعطيل حسابك الخاص")

    target.is_active = not target.is_active
    target.save()

    messages.success(
        request,
        f"تم {'تفعيل' if target.is_active else 'تعطيل'} حساب {target.full_name}",
    )

    if request.user.role == UserRole.SCHOOL_ADMIN:
        return redirect("accounts:data_entry_account_list")
    return redirect("accounts:account_list")

@super_admin_required
def account_list(request):
    accounts = User.objects.exclude(role=UserRole.SUPER_ADMIN)

    query = request.GET.get("q", "").strip()
    if query:
        accounts = accounts.filter(
            Q(full_name__icontains=query) | Q(username__icontains=query)
        )

    role_filter = request.GET.get("role", "")
    if role_filter:
        accounts = accounts.filter(role=role_filter)

    accounts = accounts.order_by("role", "full_name")

    return render(request, "accounts/account_list.html", {
        "accounts": accounts,
        "search": query,
        "role_filter": role_filter,
        "role_choices": [
            (UserRole.SCHOOL_ADMIN, "مديرة مدرسة"),
            (UserRole.DATA_ENTRY, "موظفة إدخال"),
        ],
    })


@school_admin_required
def data_entry_account_list(request):
    accounts = User.objects.filter(role=UserRole.DATA_ENTRY)

    query = request.GET.get("q", "").strip()
    if query:
        accounts = accounts.filter(
            Q(full_name__icontains=query) | Q(username__icontains=query)
        )

    accounts = accounts.order_by("full_name")

    return render(request, "accounts/data_entry_account_list.html", {
        "accounts": accounts,
        "search": query,
    })