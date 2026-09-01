from django import forms

from .models import Grade, Section, SectionSubject, Subject, Teacher


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ["number"]
        widgets = {
            "number": forms.NumberInput(attrs={"class": "app-input"}),
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


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "grades"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            "grades": forms.CheckboxSelectMultiple(),
        }


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ["full_name"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "app-input"}),
        }


class SectionSubjectForm(forms.ModelForm):
    class Meta:
        model = SectionSubject
        fields = ["section", "subject", "teacher"]
        widgets = {
            "section": forms.Select(attrs={"class": "app-input"}),
            "subject": forms.Select(attrs={"class": "app-input"}),
            "teacher": forms.Select(attrs={"class": "app-input"}),
        }