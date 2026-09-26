from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from .models import Grade, Section, SectionSubject, Subject, Teacher


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ["number"]
        widgets = {
            "number": forms.NumberInput(attrs={"class": "app-input"}),
        }
        error_messages = {
            "number": {"unique": "هذا الصف مسجّل من قبل"},
        }


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["grade", "gender", "name"]
        widgets = {
            "grade": forms.Select(attrs={"class": "app-input"}),
            "gender": forms.Select(attrs={"class": "app-input"}),
            "name": forms.TextInput(attrs={"class": "app-input"}),
        }
        error_messages = {
            NON_FIELD_ERRORS: {
                "unique_together": "هذا الفصل مسجّل من قبل بنفس الاسم والجنس لهذا الصف",
            },
        }


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "grades"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            "grades": forms.CheckboxSelectMultiple(),
        }
        error_messages = {
            "name": {"unique": "فيه مادة بهذا الاسم مسجّلة من قبل"},
        }


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ["full_name"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "app-input"}),
        }


class SectionSubjectAssignForm(forms.ModelForm):
    """
    فورم ربط فصل بمعلّمة لمادة محدَّدة مسبقًا (صفحة تفاصيل المادة) —
    المادة نفسها مو حقل بالفورم، وخيارات الفصل محصورة بصفوف المادة.
    """

    class Meta:
        model = SectionSubject
        fields = ["section", "teacher"]
        widgets = {
            "section": forms.Select(attrs={"class": "app-input"}),
            "teacher": forms.Select(attrs={"class": "app-input"}),
        }

    def __init__(self, *args, subject=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.subject = subject or (self.instance.subject if self.instance.pk else None)
        if self.subject is not None:
            self.fields["section"].queryset = Section.objects.filter(
                grade__in=self.subject.grades.all()
            ).order_by("grade__number", "gender", "name")

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        if section and self.subject and SectionSubject.objects.filter(
            section=section, subject=self.subject
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("هذا الفصل أصلاً له معلّمة مسجّلة لهذه المادة")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.subject = self.subject
        if commit:
            instance.save()
        return instance