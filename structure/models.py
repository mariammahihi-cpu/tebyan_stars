# structure/models.py — النسخة الكاملة المحدّثة

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Grade(models.Model):
    number = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        verbose_name="رقم الصف",
    )

    class Meta:
        verbose_name = "صف"
        verbose_name_plural = "الصفوف"
        ordering = ["number"]

    def __str__(self):
        return f"الصف {self.number}"


class Gender(models.TextChoices):
    BOYS = "boys", "بنين"
    GIRLS = "girls", "بنات"


class Section(models.Model):
    grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        related_name="sections",
        verbose_name="الصف",
    )
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        verbose_name="الجنس",
    )
    name = models.CharField(
        max_length=50,
        verbose_name="اسم الفصل",
        help_text="مثال: بنين، بنين 1، بنين 2، بنات",
    )

    class Meta:
        verbose_name = "فصل"
        verbose_name_plural = "الفصول"
        ordering = ["grade__number", "gender", "name"]
        unique_together = ("grade", "gender", "name")

    def __str__(self):
        return f"{self.grade} - {self.name}"


class Subject(models.Model):
    """
    مادة دراسية. مرتبطة بالصفوف اللي تُدرّس فيها عبر علاقة Many-to-Many —
    مو كل مادة موجودة بكل صف (زي ما تأكدنا سوا)، والعلاقة عكسية صحيحة
    كمان: صف واحد فيه أكتر من مادة، ومادة واحدة ممكن تتدرّس بأكتر من صف.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="اسم المادة",
    )
    grades = models.ManyToManyField(
        Grade,
        related_name="subjects",
        verbose_name="الصفوف اللي تُدرّس فيها",
    )

    class Meta:
        verbose_name = "مادة"
        verbose_name_plural = "المواد"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Teacher(models.Model):
    """معلّمة. جدول مستقل بسيط — بيانات إضافية (رقم تواصل مثلاً) ممكن تنضاف بالمستقبل بسهولة."""

    full_name = models.CharField(
        max_length=150,
        verbose_name="اسم المعلّمة",
    )

    class Meta:
        verbose_name = "معلّمة"
        verbose_name_plural = "المعلّمات"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class SectionSubject(models.Model):
    """
    جدول ربط: أي معلّمة تدرّس أي مادة لأي فصل. هذا "مكان تلاقي" بين
    Section وSubject وTeacher — بيمثّل حقيقة زي "الرياضيات بفصل 3 بنات
    بتدرّسها المعلّمة فاطمة".
    """

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="section_subjects",
        verbose_name="الفصل",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="section_subjects",
        verbose_name="المادة",
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="section_subjects",
        verbose_name="المعلّمة",
    )

    class Meta:
        verbose_name = "تدريس مادة لفصل"
        verbose_name_plural = "تدريس المواد للفصول"
        unique_together = ("section", "subject")
        ordering = ["section__grade__number", "section__name", "subject__name"]

    def clean(self):
        if self.section_id and self.subject_id:
            if not self.subject.grades.filter(pk=self.section.grade_id).exists():
                raise ValidationError(
                    "هذه المادة غير مرتبطة بصف هذا الفصل — راجعي صفوف المادة أولاً"
                )

    def __str__(self):
        return f"{self.subject} - {self.section} ({self.teacher})"