# evaluations/forms.py

from django import forms

from rules.models import RuleCategory
from students.models import Student

from .models import (
    DEFAULT_WEEKLY_CAP,
    WEEKLY_SUBJECT_CAP_KEY,
    WEEKLY_SUPERVISION_CAP_KEY,
    Evaluation,
    Settings,
)


class EvaluationForm(forms.ModelForm):
    """
    فورم تطبيق قاعدة على طالب — هذا الفورم اللي موظفة الإدخال تستخدمه يوميًا.
    فيه كل منطق التحقق (تناسق المادة مع نوع القاعدة، والسقف الأسبوعي).
    """

    class Meta:
        model = Evaluation
        fields = ["student", "rule", "subject"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-control"}),
            "rule": forms.Select(attrs={"class": "form-control"}),
            "subject": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, recorded_by=None, **kwargs):
        self.recorded_by = recorded_by
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_active=True)
        self.fields["subject"].required = False

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        rule = cleaned_data.get("rule")
        subject = cleaned_data.get("subject")

        if not student or not rule:
            return cleaned_data

        if rule.category == RuleCategory.SUBJECT and not subject:
            self.add_error("subject", "لازم تحدّدي المادة لهذه القاعدة")
            return cleaned_data

        if rule.category == RuleCategory.GENERAL and subject:
            self.add_error("subject", "قواعد الإشراف العام ما تنسجل بمادة")
            return cleaned_data

        if rule.category == RuleCategory.SUBJECT and rule.subject_id and subject != rule.subject:
            self.add_error("subject", f"هذه القاعدة خاصة بمادة {rule.subject.name} بس")
            return cleaned_data

        # فحص السقف الأسبوعي — بس على القيم الموجبة (إضافة)، الخصم مسموح دايمًا
        if rule.value > 0:
            if rule.category == RuleCategory.GENERAL:
                cap = Settings.get_int(WEEKLY_SUPERVISION_CAP_KEY, DEFAULT_WEEKLY_CAP)
                current = Evaluation.weekly_total(student, category=RuleCategory.GENERAL)
                label = "الإشراف العام"
            else:
                cap = Settings.get_int(WEEKLY_SUBJECT_CAP_KEY, DEFAULT_WEEKLY_CAP)
                current = Evaluation.weekly_total(student, subject=subject)
                label = f"مادة {subject.name}"

            if current + rule.value > cap:
                raise forms.ValidationError(
                    f"وصل الطالب/ة للسقف الأسبوعي المسموح لـ {label} ({cap} نجوم) — الرصيد الحالي {current}"
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.recorded_by = self.recorded_by
        if commit:
            instance.save()
        return instance


class WeeklySettingsForm(forms.Form):
    """
    فورم تعديل إعدادات السقف الأسبوعي. مو ModelForm عادي — لأن Settings
    جدول مفتاح/قيمة عام، وهذا الفورم يعرض بس المفتاحين المعروفين حاليًا
    كحقلين واضحين، بدل ما يعرض واجهة تقنية "مفتاح: نص، قيمة: نص".
    """

    weekly_subject_cap = forms.IntegerField(
        label="سقف نجوم المادة الأسبوعي",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    weekly_supervision_cap = forms.IntegerField(
        label="سقف نجوم الإشراف الأسبوعي",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["weekly_subject_cap"].initial = Settings.get_int(
                WEEKLY_SUBJECT_CAP_KEY, DEFAULT_WEEKLY_CAP
            )
            self.fields["weekly_supervision_cap"].initial = Settings.get_int(
                WEEKLY_SUPERVISION_CAP_KEY, DEFAULT_WEEKLY_CAP
            )

    def save(self):
        Settings.objects.update_or_create(
            key=WEEKLY_SUBJECT_CAP_KEY,
            defaults={"value": str(self.cleaned_data["weekly_subject_cap"])},
        )
        Settings.objects.update_or_create(
            key=WEEKLY_SUPERVISION_CAP_KEY,
            defaults={"value": str(self.cleaned_data["weekly_supervision_cap"])},
        )