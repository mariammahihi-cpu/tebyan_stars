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
            if self.rule.category in (RuleCategory.GENERAL, RuleCategory.REDEMPTION) and self.subject_id:
                raise ValidationError({"subject": "هذا التصنيف ما يُسجَّل بمادة معيّنة"})
            if self.rule.category == RuleCategory.SUBJECT and not self.subject_id:
                raise ValidationError({"subject": "يجب تحديد المادة لقاعدة من نوع مادة"})

            if self.rule.is_range:
                if self.value is None:
                    raise ValidationError({"value": "يجب اختيار قيمة لهذه القاعدة"})
                if not (self.rule.min_value <= self.value <= self.rule.max_value):
                    raise ValidationError({"value": "القيمة المختارة خارج المدى المسموح لهذه القاعدة"})

    def save(self, *args, **kwargs):
        if self._state.adding and self.rule_id and not self.rule.is_range:
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
    def weekly_school_totals(cls):
        """
        صافي نجوم الأسبوع الحالي على مستوى المدرسة كاملة (كل الطلاب، كل
        القواعد) — مجموع الإضافة ومجموع الخصم منفصلين، منذ آخر تصفير
        أسبوعي (أو من البداية لو ما صار تصفير أبدًا). تُستخدم بملخص لوحة
        Super Admin الإحصائي، بنفس منطق weekly_total لكن بدون تصفية طالب.
        """
        qs = cls.objects.all()
        week_start = WeeklyReset.current_week_start()
        if week_start:
            qs = qs.filter(created_at__gte=week_start)

        total_add = qs.filter(value__gt=0).aggregate(t=models.Sum("value"))["t"] or 0
        total_deduct = qs.filter(value__lt=0).aggregate(t=models.Sum("value"))["t"] or 0
        return {"add": total_add, "deduct": total_deduct, "net": total_add + total_deduct}

    @classmethod
    def cumulative_total(cls, student, *, subject=None, category=None):
        """
        المجموع التاريخي الكامل لطالب — بدون أي تصفية بالوقت. هذا هو الرصيد
        التراكمي (لوحة الشرف). تمرير subject أو category يسمح بفصل رصيد
        المواد عن رصيد الإشراف العام (أو حتى رصيد مادة واحدة بعينها)، بنفس
        منطق weekly_total.

        عند عدم تمرير subject ولا category (أي المجموع الكلي غير المصفّى)،
        يُضاف صافي أثر تحويلات "تاجر التبيان" (POSTransaction) — حتى يبقى
        الرصيد التراكمي رقمًا واحدًا متّسقًا بكل مكان بالنظام (لوحة الشرف
        والتقارير وشاشة التاجر)، بدل ما تصير التحويلات محفظة منفصلة.
        """
        qs = cls.objects.filter(student=student)
        if subject is not None:
            qs = qs.filter(subject=subject)
        if category is not None:
            qs = qs.filter(rule__category=category)
        total = qs.aggregate(total=models.Sum("value"))["total"] or 0
        if subject is None and category is None:
            total += POSTransaction.net_total(student)
        return total


class POSTransaction(models.Model):
    """
    سجل عملية تحويل رصيد نجوم تراكمي بين طرفين (طالب أو طالبة) عبر شاشة
    "تاجر التبيان" — الطرف المُحوِّل (seller) يُحوَّل من رصيده، والطرف
    المستلِم (buyer) يستلم. النظام يخدم فصول البنين والبنات معًا، فكل
    التسميات هنا محايدة عمدًا ("الطرف"، مو "الطالبة"). هذا الجدول مستقل
    عن Evaluation (شكل بيانات مختلف: طرفان لكل عملية بدل قاعدة/مادة)، لكن
    أثره على الرصيد التراكمي محسوب ضمن Evaluation.cumulative_total — بنفس
    مبدأ "بدون أي حقل رصيد منفصل يحتاج مزامنة يدوية".
    """

    buyer = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="pos_purchases",
        verbose_name="الطرف المستلِم",
    )
    seller = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="pos_sales",
        verbose_name="الطرف المُحوِّل",
    )
    amount = models.PositiveIntegerField(verbose_name="عدد النجوم المُحوَّلة")
    recorded_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_pos_transactions",
        verbose_name="سجّلتها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت التحويل")

    class Meta:
        verbose_name = "عملية تحويل (تاجر التبيان)"
        verbose_name_plural = "عمليات تحويل تاجر التبيان"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.seller} ← {self.buyer} ({self.amount})"

    @classmethod
    def net_total(cls, student):
        """صافي أثر التحويلات على رصيد الطرف: كل ما استلمه ناقص كل ما حوّله."""
        received = cls.objects.filter(buyer=student).aggregate(t=models.Sum("amount"))["t"] or 0
        sent = cls.objects.filter(seller=student).aggregate(t=models.Sum("amount"))["t"] or 0
        return received - sent