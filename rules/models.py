# rules/models.py

from django.core.exceptions import ValidationError
from django.db import models

from structure.models import Grade, Subject


class RuleCategory(models.TextChoices):
    SUBJECT = "subject", "مادة"
    GENERAL = "general", "إشراف عام"
    REDEMPTION = "redemption", "استبدال"


class Rule(models.Model):
    """
    قاعدة تقييم (إضافة أو خصم نجوم). نوعين حسب category:
    - "مادة": مرتبطة بمادة دراسية، إما مادة محددة أو كل المواد (subject فاضي).
    - "إشراف عام": قاعدة سلوك عام، مش مرتبطة بأي مادة إطلاقًا.
    """

    name = models.CharField(
        max_length=150,
        verbose_name="اسم القاعدة",
        help_text="مثال: حل الواجب، تأخر عن الحصة",
    )
    category = models.CharField(
        max_length=10,
        choices=RuleCategory.choices,
        verbose_name="التصنيف",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="rules",
        null=True,
        blank=True,
        verbose_name="مادة محددة (اختياري)",
        help_text="اتركيه فاضي لو القاعدة تنطبق على كل المواد",
    )
    grades = models.ManyToManyField(
        Grade,
        blank=True,
        related_name="redemption_rules",
        verbose_name="صفوف محددة (اختياري)",
        help_text="لقواعد الاستبدال فقط — اتركيها فاضية لتنطبق على كل الصفوف",
    )
    is_range = models.BooleanField(
        default=False,
        verbose_name="قيمة متغيّرة (مدى)",
        help_text="مفعّلة: الموظفة تختار قيمة ضمن مدى وقت التطبيق (مثال: تكليف المعلّم 1 إلى 3)",
    )
    value = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="القيمة",
        help_text="رقم موجب للإضافة، أو سالب للخصم — تُترك فاضية لو القاعدة من نوع مدى",
    )
    min_value = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="أقل قيمة بالمدى",
    )
    max_value = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="أعلى قيمة بالمدى",
    )

    class Meta:
        verbose_name = "قاعدة تقييم"
        verbose_name_plural = "قواعد التقييم"
        ordering = ["category", "name"]

    def clean(self):
        if self.is_range:
            if self.min_value is None or self.max_value is None:
                raise ValidationError("يجب تحديد أقل وأعلى قيمة لقاعدة من نوع المدى")
            if self.min_value == 0 or self.max_value == 0:
                raise ValidationError("لا يمكن أن تكون قيم المدى صفرًا")
            if self.min_value >= self.max_value:
                raise ValidationError({"min_value": "يجب أن تكون القيمة الأقل أصغر من القيمة الأعلى"})
            if (self.min_value > 0) != (self.max_value > 0):
                raise ValidationError("يجب أن تكون قيم المدى كلها موجبة (إضافة) أو كلها سالبة (خصم)")
        elif self.value is None or self.value == 0:
            raise ValidationError({"value": "لا يمكن أن تكون قيمة القاعدة صفرًا"})

        if self.category in (RuleCategory.GENERAL, RuleCategory.REDEMPTION) and self.subject_id:
            raise ValidationError(
                {"subject": "هذا التصنيف ما يرتبط بمادة معيّنة"}
            )

        if self.category == RuleCategory.REDEMPTION and not self.is_deduction:
            raise ValidationError("قواعد الاستبدال خصم فقط — لا يمكن أن تكون القيمة موجبة")

    @property
    def is_deduction(self):
        """صار true لو القاعدة (ثابتة أو مدى) تخصم نجوم بدل ما تضيفها — تُستخدم للتلوين بالواجهة."""
        if self.is_range:
            return self.min_value is not None and self.min_value < 0
        return self.value is not None and self.value < 0

    @property
    def range_values(self):
        """قايمة كل القيم الصحيحة ضمن المدى — تُستخدم لرسم أزرار الأرقام بجدول الإدخال الجماعي."""
        if not self.is_range:
            return []
        return list(range(self.min_value, self.max_value + 1))

    def __str__(self):
        if self.is_range:
            range_label = f"{self.min_value} إلى {self.max_value}"
        else:
            sign = "+" if self.value and self.value > 0 else ""
            range_label = f"{sign}{self.value}"

        if self.category in (RuleCategory.GENERAL, RuleCategory.REDEMPTION):
            return f"{self.name} ({range_label})"
        subject_label = self.subject.name if self.subject_id else "كل المواد"
        return f"{self.name} - {subject_label} ({range_label})"