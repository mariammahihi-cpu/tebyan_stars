# rules/forms.py

from django import forms

from .models import Rule, RuleCategory

RANGE_FIELD_WIDGETS = {
    # is_range تُترك بلا ودجت مخصصة عمدًا — النمط البصري (مفتاح تبديل) موحّد
    # عالميًا عبر accounts/templates/django/forms/widgets/checkbox.html.
    "value": forms.NumberInput(attrs={"class": "app-input"}),
    "min_value": forms.NumberInput(attrs={"class": "app-input"}),
    "max_value": forms.NumberInput(attrs={"class": "app-input"}),
}
RANGE_FIELD_LABELS = {
    "is_range": "قيمة متغيّرة (مدى) بدل قيمة ثابتة",
    "value": "القيمة الثابتة",
    "min_value": "أقل قيمة ( مدى)",
    "max_value": "أعلى قيمة ( مدى)",
}


class RuleForm(forms.ModelForm):
    """
    فورم كامل — إنشاء أو تعديل قاعدة بكل تفاصيلها. مخصصة لـ Super Admin بس
    (اللي عندها صلاحية كاملة على كل التصنيفات).
    """

    class Meta:
        model = Rule
        fields = ["name", "category", "subject", "grades", "is_range", "value", "min_value", "max_value"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            "category": forms.Select(attrs={"class": "app-input"}),
            "subject": forms.Select(attrs={"class": "app-input"}),
            "grades": forms.CheckboxSelectMultiple,
            **RANGE_FIELD_WIDGETS,
        }
        labels = {
            "grades": "الصفوف (لقواعد الاستبدال فقط — اتركيها فاضية لتنطبق على كل الصفوف)",
            **RANGE_FIELD_LABELS,
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self.save_m2m()
            # حماية على مستوى الخادم: حقل الصفوف معناه فقط لتصنيف "استبدال" —
            # أي قيمة توصل له لتصنيف "مادة" أو "إشراف عام" (حتى لو عبر تلاعب
            # بالواجهة) تُتجاهل هنا بغض النظر عن إخفائه بصريًا بالفورم.
            if instance.category != RuleCategory.REDEMPTION:
                instance.grades.clear()
        return instance
    
class RuleValueForm(forms.ModelForm):
    """
    فورم مصغّر — القيمة (الثابتة أو حدود المدى) بس. مخصصة لـ School Admin
    اللي صلاحيتها محصورة بتعديل قيمة قاعدة موجودة، بدون لمس اسمها أو
    تصنيفها أو المادة المرتبطة فيها أو نوعها (ثابتة/مدى).
    """

    class Meta:
        model = Rule
        fields = ["value", "min_value", "max_value"]
        widgets = {
            "value": forms.NumberInput(attrs={"class": "app-input"}),
            "min_value": forms.NumberInput(attrs={"class": "app-input"}),
            "max_value": forms.NumberInput(attrs={"class": "app-input"}),
        }
        labels = {
            "value": "القيمة الثابتة",
            "min_value": "أقل قيمة بالمدى",
            "max_value": "أعلى قيمة بالمدى",
        }


class SubjectRuleForm(forms.ModelForm):
    """فورم إضافة قاعدة مادة — التصنيف يُضبط تلقائيًا، والمادة اختيارية (فاضية = تنطبق على كل المواد)."""

    class Meta:
        model = Rule
        fields = ["name", "subject", "is_range", "value", "min_value", "max_value"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            "subject": forms.Select(attrs={"class": "app-input"}),
            **RANGE_FIELD_WIDGETS,
        }
        labels = {
            "subject": "المادة (اتركيه فاضي لتنطبق على كل المواد)",
            **RANGE_FIELD_LABELS,
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.category = RuleCategory.SUBJECT
        if commit:
            instance.save()
        return instance


class GeneralRuleForm(forms.ModelForm):
    """فورم إضافة قاعدة إشراف عام — بدون حقل مادة، والتصنيف يُضبط تلقائيًا."""

    class Meta:
        model = Rule
        fields = ["name", "is_range", "value", "min_value", "max_value"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            **RANGE_FIELD_WIDGETS,
        }
        labels = RANGE_FIELD_LABELS

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.category = RuleCategory.GENERAL
        if commit:
            instance.save()
        return instance


class RedemptionRuleForm(forms.ModelForm):
    """
    فورم إضافة قاعدة استبدال — بحقل صفوف بدل حقل مادة، والتصنيف يُضبط
    تلقائيًا. خصم فقط (يتحقق منه Rule.clean()).
    """

    class Meta:
        model = Rule
        fields = ["name", "grades", "is_range", "value", "min_value", "max_value"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            "grades": forms.CheckboxSelectMultiple,
            **RANGE_FIELD_WIDGETS,
        }
        labels = {
            "grades": "الصفوف (اتركيها فاضية لتنطبق على كل الصفوف)",
            **RANGE_FIELD_LABELS,
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.category = RuleCategory.REDEMPTION
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RedemptionRuleEditForm(forms.ModelForm):
    """
    فورم تعديل كامل لقاعدة استبدال موجودة — بلا حقل تصنيف (ثابت بعد
    الإنشاء). تُستخدم من Super Admin وSchool Admin كلاهما، لأن صلاحية
    قواعد الاستبدال تحديدًا كاملة للاثنين (خلافًا لبقية التصنيفات).
    """

    class Meta:
        model = Rule
        fields = ["name", "grades", "is_range", "value", "min_value", "max_value"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "app-input"}),
            "grades": forms.CheckboxSelectMultiple,
            **RANGE_FIELD_WIDGETS,
        }
        labels = {
            "grades": "الصفوف (اتركيها فاضية لتنطبق على كل الصفوف)",
            **RANGE_FIELD_LABELS,
        }

