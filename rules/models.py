# rules/models.py

from django.core.exceptions import ValidationError
from django.db import models

from structure.models import Subject


class RuleCategory(models.TextChoices):
    SUBJECT = "subject", "مادة"
    GENERAL = "general", "إشراف عام"


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
    value = models.IntegerField(
        verbose_name="القيمة",
        help_text="رقم موجب للإضافة، أو سالب للخصم",
    )

    class Meta:
        verbose_name = "قاعدة تقييم"
        verbose_name_plural = "قواعد التقييم"
        ordering = ["category", "name"]

    def clean(self):
        if self.value == 0:
            raise ValidationError({"value": "قيمة القاعدة ما تقدر تكون صفر"})

        if self.category == RuleCategory.GENERAL and self.subject_id:
            raise ValidationError(
                {"subject": "قواعد الإشراف العام ما ترتبط بمادة معيّنة"}
            )

    def __str__(self):
        sign = "+" if self.value > 0 else ""
        if self.category == RuleCategory.GENERAL:
            return f"{self.name} ({sign}{self.value})"
        subject_label = self.subject.name if self.subject_id else "كل المواد"
        return f"{self.name} - {subject_label} ({sign}{self.value})"