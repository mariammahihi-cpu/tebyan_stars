# students/models.py

from django.db import models

from structure.models import Section


class Student(models.Model):
    """
    سجل الطالب. عمدًا بسيط (رقم قيد + اسم + فصل بس) — نفس مبدأ البساطة
    اللي اتفقنا عليه بـ Subject سابقًا.
    """

    student_number = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="رقم القيد",
    )
    full_name = models.CharField(
        max_length=150,
        verbose_name="اسم الطالب",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="students",
        verbose_name="الفصل",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="طالب مسجّل حاليًا",
    )

    class Meta:
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"
        ordering = ["section__grade__number", "section__name", "full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.student_number})"