# leaderboard/views.py

from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.models import UserRole
from accounts.permissions import required_role
from reports.pdf import render_pdf, static_file_uri
from structure.models import Grade, Section

from .services import compute_leaderboard

TOP_N_DEFAULT = "3"
TOP_N_CHOICES = ("3", "5", "10", "all")


def _clamp_top_n(raw_value):
    return raw_value if raw_value in TOP_N_CHOICES else TOP_N_DEFAULT


def _trim(leaderboard, top_n):
    if top_n == "all":
        return leaderboard
    n = int(top_n)
    return {key: rows[:n] for key, rows in leaderboard.items()}


@required_role(UserRole.SCHOOL_ADMIN, UserRole.DATA_ENTRY)
def leaderboard_view(request):
    """
    لوحة الشرف — متاحة بنفس الشكل للأدوار الثلاثة (Super Admin مستثناة
    دائمًا من required_role وتعدي تلقائيًا، وSchool Admin وData Entry
    مُصرَّح لهما هون صراحة) بدون أي تفريق بالصلاحيات، بعكس تقارير reports
    التدقيقية. اختيار الفصل يُعيد تحميل الصفحة (نفس نمط فلاتر reports)،
    لكن تبديل التبويب (أسبوعي/تراكمي) وعدد الطلاب المعروضين (Top N) كلها
    فورية بجافاسكربت بدون أي إعادة تحميل — البيانات الكاملة للفصل تُحمَّل
    مرة وحدة بالصفحة.
    """
    grade_id = request.GET.get("grade", "").strip()
    section_id = request.GET.get("section", "").strip()

    section = None
    leaderboard = None
    if section_id:
        section = get_object_or_404(Section, pk=section_id)
        leaderboard = compute_leaderboard(section)

    sections = Section.objects.select_related("grade").all()
    sections_data = [
        {"id": s.id, "grade_id": s.grade_id, "label": str(s)}
        for s in sections
    ]

    return render(request, "leaderboard/leaderboard.html", {
        "grades": Grade.objects.all(),
        "sections": sections,
        "sections_data": sections_data,
        "selected_grade_id": grade_id,
        "selected_section_id": section_id,
        "section": section,
        "leaderboard": leaderboard,
        "top_n_default": TOP_N_DEFAULT,
    })


@required_role(UserRole.SCHOOL_ADMIN, UserRole.DATA_ENTRY)
def leaderboard_pdf(request):
    """
    تصدير PDF للوحة شرف فصل معيّن — بنفس عدد الطلاب (Top N) المختار
    بالشاشة وقت الضغط على التصدير (يُمرَّر كـquery param)، ويشمل القوائم
    الأربع كاملة (أكاديمي/سلوك × أسبوعي/تراكمي) بنفس الصفحة المطبوعة —
    ملف واحد مناسب للطباعة والتعليق بلوحة إعلانات الفصل.
    """
    section_id = request.GET.get("section", "").strip()
    if not section_id:
        return HttpResponseBadRequest("يجب اختيار فصل أولاً")

    section = get_object_or_404(Section, pk=section_id)
    top_n = _clamp_top_n(request.GET.get("top", TOP_N_DEFAULT).strip())
    leaderboard = _trim(compute_leaderboard(section), top_n)

    context = {
        "section": section,
        "leaderboard": leaderboard,
        "top_n": top_n,
        "issued_at": timezone.now(),
        "logo_uri": static_file_uri("images/logo.png"),
        "font_uri": static_file_uri("fonts/Tajawal.ttf"),
    }
    filename = f"لوحة الشرف - {section}.pdf"
    return render_pdf("leaderboard/leaderboard_pdf.html", context, filename)