# students/forms.py

from django import forms

from .models import Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["student_number", "full_name", "section"]
        widgets = {
            "student_number": forms.TextInput(attrs={"class": "form-control"}),
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "section": forms.Select(attrs={"class": "form-control"}),
        }