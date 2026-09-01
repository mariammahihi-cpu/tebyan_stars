# evaluations/models.py

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models

from rules.models import Rule, RuleCategory
from structure.models import Subject
from students.models import Student


WEEKLY_SUBJECT_CAP_KEY = "weekly_subject_cap"
WEEKLY_SUPERVISION_CAP_KEY = "weekly_supervision_cap"
DEFAULT_WEEKLY_CAP = 5


class Settings(models.Model):
    """
    جدول إعدادات عام بتصميم مفتاح/قيمة — يسمح بإضافة إعدادات جديدة
    بالمستقبل بدون أي تعديل على بنية الجدول نفسه.
    """

    key = models.CharField(max_length=100, unique=True, verbose_name="المفتاح")
    value = models.CharField(max_length=255, verbose_name="القيمة")

    class Meta:
        verbose_name = "إعداد"
        verbose_name_plural = "الإعدادات"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get_int(cls, key, default):
        try:
            return int(cls.objects.get(key=key).value)
        except (cls.DoesNotExist, ValueError, TypeError):
            return default


class WeeklyReset(models.Model):
    """
    سجل أحداث التصفير الأسبوعي — كل صف يمثّل مرة انضغط فيها زر "تصفير".
    آخر صف بيحدد "بداية الأسبوع الحالي" لكل حسابات الأرصدة الأسبوعية.
    """

    performed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="weekly_resets",
        verbose_name="نفّذت التصفير",
    )
    performed_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت التصفير")

    class Meta:
        verbose_name = "تصفير أسبوعي"
        verbose_name_plural = "سجل التصفير الأسبوعي"
        ordering = ["-performed_at"]

    def __str__(self):
        return f"تصفير بتاريخ {self.performed_at:%Y-%m-%d %H:%M}"

    @classmethod
    def current_week_start(cls):
        """وقت آخر تصفير، أو None لو ما صار تصفير أبدًا (يعني كل السجل التاريخي يُحسب أسبوع حالي)."""
        last = cls.objects.order_by("-performed_at").first()
        return last.performed_at if last else None


class Evaluation(models.Model):
    """
    سجل تطبيق قاعدة على طالب. هذا الجدول هو مصدر الحقيقة الوحيد لكل شي:
    سجل النشاط، الرصيد الأسبوعي (لكل مادة والإشراف)، والرصيد التراكمي —
    كلها تُحسب من هنا مباشرة، ما فيه أي حقل رصيد منفصل يحتاج مزامنة يدوية.
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="evaluations",
        verbose_name="الطالب",
    )
    rule = models.ForeignKey(
        Rule,
        on_delete=models.PROTECT,
        related_name="evaluations",
        verbose_name="القاعدة المطبّقة",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="evaluations",
        null=True,
        blank=True,
        verbose_name="المادة",
        help_text="فاضي تلقائيًا لقواعد الإشراف العام",
    )
    value = models.IntegerField(
        verbose_name="القيمة المطبّقة",
        help_text="نسخة من قيمة القاعدة وقت التطبيق — تبقى ثابتة حتى لو تغيّرت قيمة القاعدة لاحقًا",
    )
    recorded_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_evaluations",
        verbose_name="سجّلتها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت التسجيل")

    class Meta:
        verbose_name = "تقييم"
        verbose_name_plural = "التقييمات"
        ordering = ["-created_at"]

    def clean(self):
        if self.rule_id:
            if self.rule.category == RuleCategory.GENERAL and self.subject_id:
                raise ValidationError({"subject": "قواعد الإشراف العام ما تنسجل بمادة معيّنة"})
            if self.rule.category == RuleCategory.SUBJECT and not self.subject_id:
                raise ValidationError({"subject": "لازم تحدّدي المادة لقاعدة من نوع مادة"})

    def save(self, *args, **kwargs):
        if self._state.adding and self.value is None:
            self.value = self.rule.value
        super().save(*args, **kwargs)

    def __str__(self):
        sign = "+" if self.value > 0 else ""
        return f"{self.student} - {self.rule.name} ({sign}{self.value})"

    # --- دوال حساب الأرصدة (كل شي مشتق من هذا الجدول، بدون أي تخزين منفصل) ---

    @classmethod
    def weekly_total(cls, student, *, subject=None, category=None):
        """
        مجموع قيم التقييمات لطالب منذ آخر تصفير أسبوعي (أو من البداية لو
        ما صار تصفير أبدًا). تُستخدم لعرض الرصيد الأسبوعي وللتحقق من السقف
        قبل تطبيق قاعدة جديدة.
        """
        qs = cls.objects.filter(student=student)

        week_start = WeeklyReset.current_week_start()
        if week_start:
            qs = qs.filter(created_at__gte=week_start)

        if subject is not None:
            qs = qs.filter(subject=subject)
        if category is not None:
            qs = qs.filter(rule__category=category)

        return qs.aggregate(total=models.Sum("value"))["total"] or 0

    @classmethod
    def cumulative_total(cls, student):
        """المجموع التاريخي الكامل لطالب — بدون أي تصفية بالوقت. هذا هو الرصيد التراكمي (لوحة الشرف)."""
        return cls.objects.filter(student=student).aggregate(
            total=models.Sum("value")
        )["total"] or 0