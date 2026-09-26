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
        fields = ["student", "rule", "subject", "value"]
        widgets = {
            "student": forms.Select(attrs={"class": "app-input"}),
            "rule": forms.Select(attrs={"class": "app-input"}),
            "subject": forms.Select(attrs={"class": "app-input"}),
            "value": forms.HiddenInput(),
        }

    def __init__(self, *args, recorded_by=None, **kwargs):
        self.recorded_by = recorded_by
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_active=True)
        self.fields["subject"].required = False
        self.fields["value"].required = False

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        rule = cleaned_data.get("rule")
        subject = cleaned_data.get("subject")
        value = cleaned_data.get("value")

        if not student or not rule:
            return cleaned_data

        if rule.category == RuleCategory.SUBJECT and not subject:
            self.add_error("subject", "يجب تحديد المادة لهذه القاعدة")
            return cleaned_data

        if rule.category in (RuleCategory.GENERAL, RuleCategory.REDEMPTION) and subject:
            self.add_error("subject", "هذا التصنيف ما ينسجل بمادة")
            return cleaned_data

        if rule.category == RuleCategory.SUBJECT and rule.subject_id and subject != rule.subject:
            self.add_error("subject", f"هذه القاعدة خاصة بمادة {rule.subject.name} بس")
            return cleaned_data

        if rule.is_range:
            if value is None:
                self.add_error("value", "يجب اختيار قيمة لهذه القاعدة")
                return cleaned_data
            if not (rule.min_value <= value <= rule.max_value):
                self.add_error("value", "القيمة المختارة خارج المدى المسموح لهذه القاعدة")
                return cleaned_data
            applied_value = value
        else:
            applied_value = rule.value

        # فحص السقف الأسبوعي — بس على القيم الموجبة (إضافة)، الخصم مسموح دايمًا
        # إلا قواعد الاستبدال (REDEMPTION): خصمها مشروط بكفاية رصيد الطالب
        # المتاح للاستبدال (نفس الرقم المعروض "الرصيد" بجدول الإدخال الجماعي
        # لتبويب استبدال) — عشان ما يصير رصيد سالب بلا حد.
        if applied_value > 0:
            if rule.category == RuleCategory.GENERAL:
                cap = Settings.get_int(WEEKLY_SUPERVISION_CAP_KEY, DEFAULT_WEEKLY_CAP)
                current = Evaluation.weekly_total(student, category=RuleCategory.GENERAL)
                label = "الإشراف العام"
            else:
                cap = Settings.get_int(WEEKLY_SUBJECT_CAP_KEY, DEFAULT_WEEKLY_CAP)
                current = Evaluation.weekly_total(student, subject=subject)
                label = f"مادة {subject.name}"

            if current + applied_value > cap:
                raise forms.ValidationError(
                    f"وصل الطالب/ة للسقف الأسبوعي المسموح لـ {label} ({cap} نجوم) — الرصيد الحالي {current}"
                )
        elif rule.category == RuleCategory.REDEMPTION:
            current = Evaluation.weekly_total(student, category=RuleCategory.REDEMPTION)
            if current + applied_value < 0:
                raise forms.ValidationError("لا يوجد رصيد كافٍ لدى الطالب لتطبيق هذا الاستبدال")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.recorded_by = self.recorded_by
        if not instance.rule.is_range:
            instance.value = instance.rule.value
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
        widget=forms.NumberInput(attrs={"class": "stat-num-input"}),
    )
    weekly_supervision_cap = forms.IntegerField(
        label="سقف نجوم الإشراف الأسبوعي",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "stat-num-input"}),
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


class POSTransactionForm(forms.Form):
    """
    فورم شاشة "تاجر التبيان" — تحويل رصيد تراكمي بين طرفين (طالب أو طالبة).
    forms.Form عادي وليس ModelForm (بنفس منطق WeeklySettingsForm) لأن
    التنفيذ الفعلي يمر عبر POSService.transfer بطبقة evaluations/services.py
    — الفحص هنا مبكر وودود بس، مو الفحص النهائي الآمن ضد race conditions
    (ذاك موجود بالخدمة عبر select_for_update وقت الحفظ الفعلي).

    الحقلان buyer/seller يُعرَضان بالواجهة كحقلَي بحث مباشر (autocomplete)
    بدل قائمة منسدلة جامدة — لذا widget كل واحد منهم HiddenInput؛ الـJS
    بالقالب هو اللي يملأ قيمتهما الفعلية (id الطالب/ة المختار) بعد اختيار
    نتيجة من الاقتراحات. القيمة تبقى تُتحقَّق هنا بنفس صرامة أي ModelChoiceField
    عادي (لازم تطابق طالب/ة نشط فعليًا)، بغض النظر عن شكل واجهة الإدخال.
    """

    buyer = forms.ModelChoiceField(
        queryset=Student.objects.filter(is_active=True).order_by("full_name"),
        label="الطرف المستلِم",
        widget=forms.HiddenInput(),
        error_messages={"required": "يجب اختيار الطرف المستلِم من نتائج البحث"},
    )
    seller = forms.ModelChoiceField(
        queryset=Student.objects.filter(is_active=True).order_by("full_name"),
        label="الطرف المُحوِّل",
        widget=forms.HiddenInput(),
        error_messages={"required": "يجب اختيار الطرف المُحوِّل من نتائج البحث"},
    )
    amount = forms.IntegerField(
        min_value=1,
        label="عدد النجوم",
        widget=forms.NumberInput(attrs={"class": "app-input", "min": 1}),
    )

    def clean(self):
        cleaned_data = super().clean()
        buyer = cleaned_data.get("buyer")
        seller = cleaned_data.get("seller")
        amount = cleaned_data.get("amount")

        if buyer and seller and buyer.id == seller.id:
            raise forms.ValidationError("لا يمكن التحويل لنفس الطرف")

        # تحقق مبكر وودود قبل الوصول للخدمة — الفحص الآمن الحقيقي ضد
        # race conditions موجود في POSService.transfer عبر select_for_update.
        if seller and amount:
            current = Evaluation.cumulative_total(seller)
            if current < amount:
                raise forms.ValidationError(
                    f"لا يوجد رصيد كافٍ لدى الطرف المُحوِّل. الرصيد الحالي: {current} نجمة."
                )

        return cleaned_data