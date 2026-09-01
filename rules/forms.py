# rules/forms.py

from django import forms

from .models import Rule


class RuleForm(forms.ModelForm):
    """
    فورم كامل — إنشاء أو تعديل قاعدة بكل تفاصيلها. مخصصة لـ Super Admin بس
    (اللي عندها صلاحية كاملة).
    """

    class Meta:
        model = Rule
        fields = ["name", "category", "subject", "value"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "subject": forms.Select(attrs={"class": "form-control"}),
            "value": forms.NumberInput(attrs={"class": "form-control"}),
        }


class RuleValueForm(forms.ModelForm):
    """
    فورم مصغّر — حقل القيمة بس. مخصصة لـ School Admin اللي صلاحيتها محصورة
    بتعديل قيمة قاعدة موجودة، بدون لمس اسمها أو تصنيفها أو المادة المرتبطة فيها.
    """

    class Meta:
        model = Rule
        fields = ["value"]
        widgets = {
            "value": forms.NumberInput(attrs={"class": "form-control"}),
        }