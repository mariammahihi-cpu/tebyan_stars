from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import required_role, super_admin_required

from .forms import GradeForm, SectionForm, SubjectForm
from .models import Grade, Section, Subject

from django.db.models import Count
from .forms import GradeForm, SectionForm, SectionSubjectForm, SubjectForm, TeacherForm
from .models import Grade, Section, SectionSubject, Subject, Teacher


# ---------------------------------------------------------------------------
# دوال مساعدة داخلية (مو views مربوطة بمسارات مباشرة) — منطق مشترك بين
# الموديلات التلاتة (Grade/Section/Subject) بما إنه عندهم نفس نمط الصلاحيات
# ونفس نمط العمليات (عرض+إضافة، تعديل، حذف) بالضبط.
# ---------------------------------------------------------------------------

def _list_and_create(request, *, model, form_class, template_name, context_key, initial=None):
    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("هذه الصفحة للعرض بس — الإضافة محصورة بمسؤولة النظام")

        form = form_class(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت الإضافة بنجاح")
            return redirect(request.path)
    else:
        form = form_class(initial=initial)

    return render(request, template_name, {
        context_key: model.objects.all(),
        "form": form,
    })


def _edit_object(request, *, model, form_class, pk, template_name, redirect_url_name):
    obj = get_object_or_404(model, pk=pk)

    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            form.save()
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



@super_admin_required
def edit_grade(request, pk):
    return _edit_object(
        request,
        model=Grade,
        form_class=GradeForm,
        pk=pk,
        template_name="structure/edit_object.html",
        redirect_url_name="structure:manage_grades",
    )


@require_POST
@super_admin_required
def delete_grade(request, pk):
    return _delete_object(
        request,
        model=Grade,
        pk=pk,
        redirect_url_name="structure:manage_grades",
        protected_message="لا يمكن حذف هذا الصف لأنه مرتبط بفصول موجودة — احذفي الفصول أولاً",
    )


# ---------------------------------------------------------------------------
# الفصول (Section)
# ---------------------------------------------------------------------------

@required_role(UserRole.SCHOOL_ADMIN)
def manage_sections(request):
    return _list_and_create(
        request,
        model=Section,
        form_class=SectionForm,
        template_name="structure/manage_sections.html",
        context_key="sections",
    )


@super_admin_required
def edit_section(request, pk):
    return _edit_object(
        request,
        model=Section,
        form_class=SectionForm,
        pk=pk,
        template_name="structure/edit_object.html",
        redirect_url_name="structure:manage_sections",
    )


@require_POST
@super_admin_required
def delete_section(request, pk):
    return _delete_object(
        request,
        model=Section,
        pk=pk,
        redirect_url_name="structure:manage_sections",
        protected_message="لا يمكن حذف هذا الفصل — تأكدي إنه غير مستخدم بمكان تاني بالنظام",
    )


# ---------------------------------------------------------------------------
# المواد (Subject)
# ---------------------------------------------------------------------------

@required_role(UserRole.SCHOOL_ADMIN)
def manage_subjects(request):
    return _list_and_create(
        request,
        model=Subject,
        form_class=SubjectForm,
        template_name="structure/manage_subjects.html",
        context_key="subjects",
    )


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
    return _list_and_create(
        request,
        model=Teacher,
        form_class=TeacherForm,
        template_name="structure/manage_teachers.html",
        context_key="teachers",
    )


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
# ربط فصل + مادة + معلّمة (SectionSubject)
# ---------------------------------------------------------------------------

@required_role(UserRole.SCHOOL_ADMIN)
def manage_section_subjects(request):
    initial = {}
    teacher_id = request.GET.get("teacher")
    if teacher_id:
        initial["teacher"] = teacher_id

    return _list_and_create(
        request,
        model=SectionSubject,
        form_class=SectionSubjectForm,
        template_name="structure/manage_section_subjects.html",
        context_key="section_subjects",
        initial=initial,
    )

@super_admin_required
def edit_section_subject(request, pk):
    return _edit_object(
        request,
        model=SectionSubject,
        form_class=SectionSubjectForm,
        pk=pk,
        template_name="structure/edit_object.html",
        redirect_url_name="structure:manage_section_subjects",
    )


@require_POST
@super_admin_required
def delete_section_subject(request, pk):
    return _delete_object(
        request,
        model=SectionSubject,
        pk=pk,
        redirect_url_name="structure:manage_section_subjects",
        protected_message="تعذّر حذف هذا الربط",
    )