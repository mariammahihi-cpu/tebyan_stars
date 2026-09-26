from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import required_role, super_admin_required

from .forms import GradeForm, SectionForm, SectionSubjectAssignForm, SubjectForm, TeacherForm
from .models import Grade, Section, SectionSubject, Subject, Teacher


# ---------------------------------------------------------------------------
# دوال مساعدة داخلية (مو views مربوطة بمسارات مباشرة) — منطق تعديل وحذف
# مشترك بين كل موديلات الهيكل التنظيمي، لأنها نفس النمط بالضبط.
# ---------------------------------------------------------------------------

def _edit_object(request, *, model, form_class, pk, template_name, redirect_url_name):
    obj = get_object_or_404(model, pk=pk)

    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, "هذه القيمة مستخدمة من قبل بعنصر تاني")
            else:
                messages.success(request, "تم التعديل بنجاح")
                return redirect(redirect_url_name)
    else:
        form = form_class(instance=obj)

    return render(request, template_name, {"form": form, "object": obj})


def _delete_object(request, *, model, pk, redirect_url_name, protected_message):
    obj = get_object_or_404(model, pk=pk)
    try:
        obj.delete()
        messages.success(request, "تم الحذف بنجاح")
    except ProtectedError:
        # صار لما تحاولي تحذفي صف لسا فيه فصول مرتبطة فيه (on_delete=PROTECT)
        messages.error(request, protected_message)
    return redirect(redirect_url_name)


# ---------------------------------------------------------------------------
# الصفوف (Grade)
# ---------------------------------------------------------------------------

@required_role(UserRole.SCHOOL_ADMIN)
def grade_list(request):
    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("الإضافة محصورة بمسؤولة النظام")
        form = GradeForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error("number", "هذا الصف مسجّل من قبل")
            else:
                messages.success(request, "تمت إضافة الصف بنجاح")
                return redirect("structure:grade_list")
    else:
        form = GradeForm()

    grades = Grade.objects.annotate(
        student_count=Count("sections__students", distinct=True)
    )

    return render(request, "structure/grade_list.html", {
        "grades": grades,
        "form": form,
    })


@super_admin_required
def edit_grade(request, pk):
    return _edit_object(
        request,
        model=Grade,
        form_class=GradeForm,
        pk=pk,
        template_name="structure/edit_object.html",
        redirect_url_name="structure:grade_list",
    )


@require_POST
@super_admin_required
def delete_grade(request, pk):
    return _delete_object(
        request,
        model=Grade,
        pk=pk,
        redirect_url_name="structure:grade_list",
        protected_message="لا يمكن حذف هذا الصف لأنه مرتبط بفصول موجودة — احذفي الفصول أولاً",
    )


# ---------------------------------------------------------------------------
# الفصول (Section)
# ---------------------------------------------------------------------------

@required_role(UserRole.SCHOOL_ADMIN)
def section_list(request, grade_id):
    grade = get_object_or_404(Grade, pk=grade_id)

    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("الإضافة محصورة بمسؤولة النظام")
        form = SectionForm(request.POST, initial={"grade": grade})
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, "هذا الفصل مسجّل من قبل بنفس الاسم والجنس لهذا الصف")
            else:
                messages.success(request, "تمت إضافة الفصل بنجاح")
                return redirect("structure:section_list", grade_id=grade.id)
    else:
        form = SectionForm(initial={"grade": grade})

    sections = Section.objects.filter(grade=grade).annotate(
        student_count=Count("students", distinct=True)
    )

    return render(request, "structure/section_list.html", {
        "grade": grade,
        "sections": sections,
        "form": form,
    })


@super_admin_required
def edit_section(request, pk):
    section = get_object_or_404(Section, pk=pk)

    if request.method == "POST":
        form = SectionForm(request.POST, instance=section)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, "هذا الفصل مسجّل من قبل بنفس الاسم والجنس لهذا الصف")
            else:
                messages.success(request, "تم التعديل بنجاح")
                return redirect("structure:section_list", grade_id=section.grade_id)
    else:
        form = SectionForm(instance=section)

    return render(request, "structure/edit_object.html", {"form": form, "object": section})


@require_POST
@super_admin_required
def delete_section(request, pk):
    section = get_object_or_404(Section, pk=pk)
    grade_id = section.grade_id
    try:
        section.delete()
        messages.success(request, "تم حذف الفصل بنجاح")
    except ProtectedError:
        messages.error(request, "لا يمكن حذف هذا الفصل — تأكدي إنه غير مستخدم بمكان تاني بالنظام")
    return redirect("structure:section_list", grade_id=grade_id)


# ---------------------------------------------------------------------------
# المواد (Subject)
# ---------------------------------------------------------------------------

# أيقونة ولون مناسبين لكل مادة حسب اسمها — مطابقة كلمات مفتاحية عربية شائعة،
# مجرد عرض بصري (ما يُخزَّن، وما يحتاج حقل إضافي بالنموذج). أي اسم ما طابق
# كلمة معروفة ياخذ الشكل الافتراضي (أخضر العلامة التجارية).
_SUBJECT_VISUALS = [
    (["رياضيات", "حساب"], "fa-calculator", "bg-blue-50", "text-blue-600"),
    (["انجليز", "إنجليز", "english"], "fa-language", "bg-indigo-50", "text-indigo-600"),
    (["عربي", "نحو", "قراءة", "إملاء"], "fa-book-open", "bg-emerald-50", "text-emerald-700"),
    (["علوم"], "fa-flask", "bg-purple-50", "text-purple-600"),
    (["حاسوب", "حاسب", "كمبيوتر", "برمجة", "تقنية"], "fa-laptop-code", "bg-slate-100", "text-slate-600"),
    (["اجتماعيات", "جغراف", "تاريخ", "وطني"], "fa-earth-africa", "bg-teal-50", "text-teal-600"),
    (["إسلام", "اسلام", "دين", "قرآن", "تجويد", "فقه"], "fa-moon", "bg-amber-50", "text-amber-600"),
    (["فن", "رسم"], "fa-palette", "bg-pink-50", "text-pink-600"),
    (["رياضة", "بدني"], "fa-person-running", "bg-orange-50", "text-orange-600"),
    (["موسيق"], "fa-music", "bg-rose-50", "text-rose-600"),
]


def _subject_visual(name):
    for keywords, icon, bg, text in _SUBJECT_VISUALS:
        if any(keyword in name for keyword in keywords):
            return {"icon": icon, "bg": bg, "text": text}
    return {"icon": "fa-book", "bg": "bg-brand-dark/10", "text": "text-brand-dark"}


@required_role(UserRole.SCHOOL_ADMIN)
def manage_subjects(request):
    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("الإضافة محصورة بمسؤولة النظام")
        form = SubjectForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error("name", "فيه مادة بهذا الاسم مسجّلة من قبل")
            else:
                messages.success(request, "تمت إضافة المادة بنجاح")
                return redirect("structure:manage_subjects")
    else:
        form = SubjectForm()

    subjects = list(
        Subject.objects.annotate(
            section_count=Count("section_subjects", distinct=True)
        ).prefetch_related("grades")
    )
    for subject in subjects:
        subject.visual = _subject_visual(subject.name)

    return render(request, "structure/manage_subjects.html", {
        "subjects": subjects,
        "form": form,
    })


@required_role(UserRole.SCHOOL_ADMIN)
def subject_detail(request, pk):
    subject = get_object_or_404(Subject, pk=pk)

    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("الإضافة محصورة بمسؤولة النظام")
        form = SectionSubjectAssignForm(request.POST, subject=subject)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error("section", "هذا الفصل أصلاً له معلّمة مسجّلة لهذه المادة")
            else:
                messages.success(request, "تمت إضافة الربط بنجاح")
                return redirect("structure:subject_detail", pk=subject.pk)
    else:
        form = SectionSubjectAssignForm(subject=subject)

    assignments = subject.section_subjects.select_related("section", "section__grade", "teacher")

    return render(request, "structure/subject_detail.html", {
        "subject": subject,
        "assignments": assignments,
        "form": form,
    })


@super_admin_required
def edit_subject(request, pk):
    return _edit_object(
        request,
        model=Subject,
        form_class=SubjectForm,
        pk=pk,
        template_name="structure/edit_object.html",
        redirect_url_name="structure:manage_subjects",
    )


@require_POST
@super_admin_required
def delete_subject(request, pk):
    return _delete_object(
        request,
        model=Subject,
        pk=pk,
        redirect_url_name="structure:manage_subjects",
        protected_message="لا يمكن حذف هذه المادة — تأكدي إنها غير مستخدمة بمكان تاني بالنظام",
    )

# ---------------------------------------------------------------------------
# المعلّمات (Teacher)
# ---------------------------------------------------------------------------

@required_role(UserRole.SCHOOL_ADMIN)
def manage_teachers(request):
    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("الإضافة محصورة بمسؤولة النظام")
        form = TeacherForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة المعلّمة بنجاح")
            return redirect("structure:manage_teachers")
    else:
        form = TeacherForm()

    teachers = list(
        Teacher.objects.annotate(
            link_count=Count("section_subjects", distinct=True)
        ).prefetch_related("section_subjects__subject")
    )
    for teacher in teachers:
        seen_subject_ids = set()
        subject_names = []
        for section_subject in teacher.section_subjects.all():
            if section_subject.subject_id not in seen_subject_ids:
                seen_subject_ids.add(section_subject.subject_id)
                subject_names.append(section_subject.subject.name)
        teacher.subject_names = subject_names

    return render(request, "structure/manage_teachers.html", {
        "teachers": teachers,
        "form": form,
    })


@required_role(UserRole.SCHOOL_ADMIN)
def teacher_detail(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    assignments = teacher.section_subjects.select_related("section", "section__grade", "subject")

    return render(request, "structure/teacher_detail.html", {
        "teacher": teacher,
        "assignments": assignments,
    })


@super_admin_required
def edit_teacher(request, pk):
    return _edit_object(
        request,
        model=Teacher,
        form_class=TeacherForm,
        pk=pk,
        template_name="structure/edit_object.html",
        redirect_url_name="structure:manage_teachers",
    )


@require_POST
@super_admin_required
def delete_teacher(request, pk):
    return _delete_object(
        request,
        model=Teacher,
        pk=pk,
        redirect_url_name="structure:manage_teachers",
        protected_message="لا يمكن حذف هذه المعلّمة — لسا مرتبطة بتدريس مادة لفصل، احذفي الربط أولاً",
    )


# ---------------------------------------------------------------------------
# ربط فصل + مادة + معلّمة (SectionSubject) — تُدار من صفحة تفاصيل المادة
# ---------------------------------------------------------------------------

@super_admin_required
def edit_section_subject(request, pk):
    assignment = get_object_or_404(SectionSubject, pk=pk)

    if request.method == "POST":
        form = SectionSubjectAssignForm(request.POST, instance=assignment, subject=assignment.subject)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error("section", "هذا الفصل أصلاً له معلّمة مسجّلة لهذهٍ المادة")
            else:
                messages.success(request, "تم التعديل بنجاح")
                return redirect("structure:subject_detail", pk=assignment.subject_id)
    else:
        form = SectionSubjectAssignForm(instance=assignment, subject=assignment.subject)

    return render(request, "structure/edit_object.html", {"form": form, "object": assignment})


@require_POST
@super_admin_required
def delete_section_subject(request, pk):
    assignment = get_object_or_404(SectionSubject, pk=pk)
    subject_id = assignment.subject_id
    assignment.delete()
    messages.success(request, "تم حذف الربط بنجاح")
    return redirect("structure:subject_detail", pk=subject_id)