# accounts/models.py

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UserRole(models.TextChoices):
    """الأدوار الثلاثة الثابتة بالنظام. ما فيه دور رابع أو صلاحيات مخصصة أكثر من هذا حاليًا."""
    SUPER_ADMIN = "super_admin", "مسؤولة النظام (صلاحية كاملة)"
    SCHOOL_ADMIN = "school_admin", "مديرة المدرسة"
    DATA_ENTRY = "data_entry", "موظفة إدخال البيانات"


class UserManager(BaseUserManager):
    """
    مدير مخصص لأن User ما بيرث من AbstractUser الجاهز.
    مسؤول عن إنشاء المستخدمين (create_user) وحساب المسؤولة الأساسية (create_superuser).
    """

    use_in_migrations = True

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("اسم المستخدم (username) مطلوب")
        if not extra_fields.get("role"):
            raise ValueError("يجب تحديد دور (role) صريح عند إنشاء أي حساب")

        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        # حساب المسؤولة الأساسية (Super Admin) دايمًا بيُنشأ بهذا الدور، بدون ما نحتاج نمرره يدويًا
        extra_fields["role"] = UserRole.SUPER_ADMIN
        extra_fields.setdefault("full_name", username)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser):
    """
    مستخدم النظام. يمثل الأدوار الثلاثة (Super Admin / School Admin / Data Entry)
    عبر حقل role بس، بدون أي ربط بنظام صلاحيات Django الجاهز (Groups/Permissions).

    is_staff و is_superuser موجودين فقط عشان Super Admin تقدر تستخدم لوحة
    /admin الجاهزة كأداة احتياطية للتطوير والتصحيح — وليس كنقطة دخول رسمية
    للنظام (نقطة الدخول الرسمية هي صفحة تسجيل الدخول المخصصة اللي بنبنيها إحنا).
    """

    username = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="اسم المستخدم",
    )
    full_name = models.CharField(
        max_length=150,
        verbose_name="الاسم الكامل",
    )
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        verbose_name="الدور",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="الحساب مفعّل",
    )
    is_staff = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="يقدر يدخل لوحة /admin",
    )
    is_superuser = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="صلاحية كاملة بلوحة /admin",
    )
    date_joined = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ إنشاء الحساب",
    )

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # is_staff/is_superuser مشتقّين تلقائيًا من role دايمًا — مو حقول تُملأ يدويًا
        # من أي فورم أو مكان تاني، عشان محدش يقدر (حتى بالغلط) يمنح صلاحية لوحة
        # /admin لحساب مش Super Admin.
        is_super = self.role == UserRole.SUPER_ADMIN
        self.is_staff = is_super
        self.is_superuser = is_super
        super().save(*args, **kwargs)

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    @property
    def is_super_admin(self):
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_school_admin(self):
        return self.role == UserRole.SCHOOL_ADMIN

    @property
    def is_data_entry(self):
        return self.role == UserRole.DATA_ENTRY