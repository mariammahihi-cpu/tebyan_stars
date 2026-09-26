# reports/views.py

import io
import zipfile

from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import required_role, school_admin_required
from evaluations.models import Evaluation, POSTransaction

from structure.models import Grade, Section, SectionSubject, Subject, Teacher
from students.models import Student

from .pdf import content_disposition_header, render_pdf, render_pdf_bytes, static_file_uri
from .services import compute_performance_trend

TREND_DISPLAY = {
    "improved": {"label": "تحسّن", "icon": "▲", "color": "#1B5E20"},
    "declined": {"label": "تراجع", "icon": "▼", "color": "#B91C1C"},
    "stable": {"label": "مستقر", "icon": "■", "color": "#92400E"},
    None: {"label": "غير متاح بعد", "icon": "–", "color": "#64748B"},
}


def _parent_report_context(student):
    """
    السياق الكامل لتقرير ولي أمر طالب واحد — دالة مشتركة يستخدمها كل من
    parent_report (تنزيل ملف واحد) وbulk_parent_reports (تصدير جماعي داخل
    أرشيف ZIP)، عشان ما يتكرر بناء نفس البيانات بمكانين.
    """
    entries = Evaluation.objects.filter(student=student).select_related(
        "rule", "subject"
    ).order_by("-created_at")

    # عمليات تاجر التبيان اللي شارك فيها الطالب (محوِّلًا أو مستلمًا) —
    # بدون بيانات تدقيقية (لا هوية الموظفة، لا وقت دقيق) بنفس قيد باقي
    # تقرير ولي الأمر، فقط التاريخ والمبلغ والطرف الآخر.
    pos_transactions = []
    for tx in (
        POSTransaction.objects.filter(Q(seller=student) | Q(buyer=student))
        .select_related("seller", "buyer")
        .order_by("-created_at")
    ):
        if tx.seller_id == student.id:
            description = f"حوّل {tx.amount} نجمة إلى {tx.buyer.full_name}"
        else:
            description = f"استلم {tx.amount} نجمة من {tx.seller.full_name}"
        pos_transactions.append({"date": tx.created_at, "description": description})

    return {
        "student": student,
        "section": student.section,
        "entries": entries,
        "pos_transactions": pos_transactions,
        "weekly_total": Evaluation.weekly_total(student),
        "cumulative_total": Evaluation.cumulative_total(student),
        "trend": TREND_DISPLAY[compute_performance_trend(student)],
        "issued_at": timezone.now(),
        "logo_uri": static_file_uri("images/logo.png"),
        "font_uri": static_file_uri("fonts/Tajawal.ttf"),
    }

@required_role(UserRole.SCHOOL_ADMIN, UserRole.DATA_ENTRY)
def parent_report(request, student_id):
    """
    تقرير أداء طالب واحد بصيغة PDF، مُعَدّ للتسليم لولي الأمر — بلا أي
    بيانات تدقيقية (لا وقت دقيق، ولا هوية موظفة الإدخال). متاح لموظفة
    الإدخال والمديرة/المسؤولة، بعكس تقريري المعلّمة والمديرة (محصورين
    بالمديرة/المسؤولة فقط).
    """
    student = get_object_or_404(Student, pk=student_id)
    context = _parent_report_context(student)
    filename = f"تقرير ولي أمر - {student.full_name}.pdf"
    return render_pdf("reports/parent_report.html", context, filename)


@require_POST
@required_role(UserRole.SCHOOL_ADMIN, UserRole.DATA_ENTRY)
def bulk_parent_reports(request):
    """
    تصدير جماعي: تقرير ولي أمر منفصل (ملف PDF مستقل) لكل طالب من مجموعة
    محدّدة — كل الملفات تُجمَّع داخل أرشيف ZIP واحد للتنزيل، عشان يسهل على
    الموظفة إرسال كل ملف لولي أمره لحاله (بعكس ملف واحد مجمّع للكل).
    """
    student_ids = request.POST.getlist("students")
    if not student_ids:
        return HttpResponseBadRequest("لا يوجد طلاب محدّدين")

    students = Student.objects.filter(id__in=student_ids)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for student in students:
            context = _parent_report_context(student)
            pdf_bytes = render_pdf_bytes("reports/parent_report.html", context)

            # رقم القيد فريد لكل طالب (unique بالنموذج)، فيضمن اسم ملف
            # فريد داخل الأرشيف حتى لو تكرر اسم طالبتين بالضبط
            entry_name = f"{student.full_name} ({student.student_number}).pdf"
            zip_file.writestr(entry_name, pdf_bytes)

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = content_disposition_header(
        "تقارير أولياء الأمور.zip", "parent-reports.zip"
    )
    return response


@school_admin_required
def teacher_report(request, teacher_id):
    """
    تقرير بأداء طلاب كل فصل/مادة مُسندة لمعلّمة معيّنة — النطاق يُستعلَم
    تلقائيًا من SectionSubject (حقيقة "مين تدرّس مين")، فلا يظهر أي فصل أو
    مادة خارج تكليفها الفعلي إطلاقًا. بلا بيانات تدقيقية (لا وقت دقيق، ولا
    هوية موظفة الإدخال) — محصور بالمديرة/المسؤولة فقط.

    قواعد الإشراف العام مستبعدة من هذا التقرير عمدًا: هي غير مرتبطة بأي
    مادة أصلاً (Evaluation.subject فاضي لها دايمًا)، فما تقع ضمن تكليف أي
    معلّمة مادة بحكم تصميم البيانات نفسه — مو خيارًا تعسفيًا.
    """
    teacher = get_object_or_404(Teacher, pk=teacher_id)

    assignments = list(
        SectionSubject.objects.filter(teacher=teacher)
        .select_related("section", "section__grade", "subject")
        .order_by("subject__name", "section__grade__number", "section__name")
    )

    summary_rows = []
    pairs_query = Q()
    for index, assignment in enumerate(assignments):
        section = assignment.section
        subject = assignment.subject
        pairs_query = (
            Q(student__section=section, subject=subject)
            if index == 0
            else pairs_query | Q(student__section=section, subject=subject)
        )

        for student in Student.objects.filter(section=section, is_active=True).order_by("full_name"):
            summary_rows.append({
                "student": student,
                "section": section,
                "subject": subject,
                "weekly": Evaluation.weekly_total(student, subject=subject),
                "cumulative": Evaluation.cumulative_total(student, subject=subject),
                "trend": TREND_DISPLAY[compute_performance_trend(student, subject=subject)],
            })

    entries = (
        Evaluation.objects.filter(pairs_query)
        .select_related("student", "student__section", "rule", "subject")
        .order_by("student__full_name", "-created_at")
        if assignments else Evaluation.objects.none()
    )

    context = {
        "teacher": teacher,
        "assignments": assignments,
        "summary_rows": summary_rows,
        "entries": entries,
        "issued_at": timezone.now(),
        "logo_uri": static_file_uri("images/logo.png"),
        "font_uri": static_file_uri("fonts/Tajawal.ttf"),
    }

    filename = f"تقرير معلّمة - {teacher.full_name}.pdf"
    return render_pdf("reports/teacher_report.html", context, filename)


@school_admin_required
def admin_report_filters(request):
    """
    صفحة اختيار فلاتر تقرير المديرة، قبل توليد الـPDF — تعرض قوائم
    الطلاب/الفصول/المواد/المعلّمات عشان تختار المديرة أي تركيبة فلترة
    (فلتر واحد أو عدة فلاتر مع بعض)، وزر "توليد التقرير" يرسل نفس
    المعايير كـquery params لـadmin_report_pdf.
    """
    context = {
        "students": Student.objects.filter(is_active=True)
        .select_related("section")
        .order_by("section__grade__number", "section__name", "full_name"),
        "sections": Section.objects.select_related("grade").all(),
        "subjects": Subject.objects.all(),
        "teachers": Teacher.objects.all(),
    }
    return render(request, "reports/admin_report_filters.html", context)


@school_admin_required
def admin_report_pdf(request):
    """
    تقرير المديرة: سجل تقييمات مفلتر بحرية (طالب/فصل/مادة/معلّمة — منفردة
    أو مجتمعة معًا)، ويشمل كل الحقول التدقيقية (وقت التسجيل بالدقيقة،
    وهوية موظفة الإدخال) بعكس تقريري المعلّمة وولي الأمر. محصور بالمديرة
    والمسؤولة فقط.

    رصيد ملخص كل طالب يُحسب حسب فلتر المادة لو محدّد (رصيد تلك المادة
    فقط)، أو الرصيد الكلي (كل المواد + الإشراف) لو ما فيه فلتر مادة —
    بنفس منطق تقرير ولي الأمر. الطلاب الظاهرون بالملخص هم فقط من لديهم
    تقييمات مطابقة للفلترة الحالية (تقرير تدقيقي يعكس السجلات الفعلية،
    بعكس تقرير المعلّمة اللي يسرد كل طالبات نطاقها حتى بلا تقييمات).
    """
    student_id = request.GET.get("student")
    section_id = request.GET.get("section")
    subject_id = request.GET.get("subject")
    teacher_id = request.GET.get("teacher")

    if not any([student_id, section_id, subject_id, teacher_id]):
        return HttpResponseBadRequest("اختاري فلترًا واحدًا على الأقل")

    entries = Evaluation.objects.select_related(
        "student", "student__section", "rule", "subject", "recorded_by"
    )

    filters_display = []
    subject = None

    if student_id:
        student = get_object_or_404(Student, pk=student_id)
        entries = entries.filter(student=student)
        filters_display.append(f"الطالب: {student.full_name}")

    if section_id:
        section = get_object_or_404(Section, pk=section_id)
        entries = entries.filter(student__section=section)
        filters_display.append(f"الفصل: {section}")

    if subject_id:
        subject = get_object_or_404(Subject, pk=subject_id)
        entries = entries.filter(subject=subject)
        filters_display.append(f"المادة: {subject.name}")

    if teacher_id:
        teacher = get_object_or_404(Teacher, pk=teacher_id)
        assignments = SectionSubject.objects.filter(teacher=teacher)
        pairs_query = Q()
        for assignment in assignments:
            pairs_query |= Q(student__section=assignment.section, subject=assignment.subject)
        entries = entries.filter(pairs_query) if assignments.exists() else entries.none()
        filters_display.append(f"المعلّمة: {teacher.full_name}")

    entries = entries.order_by("-created_at")

    students_in_scope = Student.objects.filter(
        id__in=entries.values_list("student_id", flat=True).distinct()
    ).select_related("section").order_by("full_name")

    summary_rows = [
        {
            "student": student_obj,
            "weekly": Evaluation.weekly_total(student_obj, subject=subject),
            "cumulative": Evaluation.cumulative_total(student_obj, subject=subject),
            "trend": TREND_DISPLAY[compute_performance_trend(student_obj, subject=subject)],
        }
        for student_obj in students_in_scope
    ]

    context = {
        "filters_display": filters_display,
        "summary_rows": summary_rows,
        "entries": entries,
        "issued_at": timezone.now(),
        "logo_uri": static_file_uri("images/logo.png"),
        "font_uri": static_file_uri("fonts/Tajawal.ttf"),
    }
    return render_pdf("reports/admin_report.html", context, "تقرير المديرة.pdf")

@required_role(UserRole.SCHOOL_ADMIN, UserRole.DATA_ENTRY)
def parent_report_picker(request):
    """
    صفحة اختيار طالب (أو عدة طلاب) لتصدير تقرير ولي الأمر — مدخل موحّد
    لموظفة الإدخال والمديرة/المسؤولة للوصول لتصدير تقرير ولي الأمر (فردي
    أو جماعي ZIP)، بدون الحاجة للتنقل عبر هيكل الصفوف/الفصول اللي موظفة
    الإدخال أصلاً ما عندها صلاحية وصول له (classroom_roster وstudent_detail
    محصوران بالمديرة/المسؤولة). فلترة بالصف والفصل، وبحث بالاسم أو رقم
    القيد، وفلتر "أعلى 5 رصيدًا" (رصيد تراكمي) يظهر فقط بعد اختيار فصل
    معيّن — مو منطقي عرضه على مستوى المدرسة كاملة بما إن كل فصل له سقفه
    الأسبوعي الخاص، فالمقارنة العادلة تكون بين طالبات نفس الفصل بس.
    """
    grade_id = request.GET.get("grade", "").strip()
    section_id = request.GET.get("section", "").strip()
    query = request.GET.get("q", "").strip()
    top5 = request.GET.get("top5") == "1" and bool(section_id)

    students = Student.objects.filter(is_active=True).select_related("section", "section__grade")
    if grade_id:
        students = students.filter(section__grade_id=grade_id)
    if section_id:
        students = students.filter(section_id=section_id)
    if query:
        students = students.filter(
            Q(full_name__icontains=query) | Q(student_number__icontains=query)
        )

    top5_totals = {}
    if top5:
        # ترتيب مسبق حسب الرصيد التراكمي داخل الفصل — استعلام تجميعي واحد،
        # بعدها نقتصر على أعلى 5 أرقام طلاب ونحافظ على نفس ترتيبهم بالعرض.
        ranked = list(
            Evaluation.objects.filter(student__section_id=section_id)
            .values("student_id")
            .annotate(total=Sum("value"))
            .order_by("-total")[:5]
        )
        top5_totals = {row["student_id"]: row["total"] for row in ranked}
        top_ids = list(top5_totals.keys())
        students_by_id = {s.id: s for s in students.filter(id__in=top_ids)}
        students = []
        for student_id in top_ids:
            student = students_by_id.get(student_id)
            if student is not None:
                student.cumulative_balance = top5_totals[student_id]
                students.append(student)
    else:
        students = students.order_by("section__grade__number", "section__name", "full_name")

    return render(request, "reports/parent_report_picker.html", {
        "students": students,
        "search_q": query,
        "grades": Grade.objects.all(),
        "sections": Section.objects.filter(grade_id=grade_id) if grade_id else Section.objects.select_related("grade").all(),
        "selected_grade_id": grade_id,
        "selected_section_id": section_id,
        "top5": top5,
    })