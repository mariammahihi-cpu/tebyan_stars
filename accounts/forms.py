from django import forms
from django.contrib.auth import authenticate
from .models import User, UserRole
from .models import User
from django.contrib.auth import password_validation


class LoginForm(forms.Form):
    """
    فورم تسجيل دخول موحد للأدوار الثلاثة كلها (Super Admin / School Admin / Data Entry).
    عمدًا ما فيه حقل لاختيار الدور — الدور بيتحدد تلقائيًا من حساب المستخدم
    نفسه بعد التحقق من username/password، مو من اختيار بالفورم. هيك ما فيه
    احتمال إن حد "يختار" دور أعلى من اللي عنده فعليًا بالواجهة.
    """

    username = forms.CharField(
        label="اسم المستخدم",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "autofocus": True,
            "placeholder": "اكتبي اسم المستخدم",
        }),
    )
    password = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "اكتبي كلمة المرور",
        }),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if not username or not password:
            return cleaned_data

        # فحص مسبق خاص بالحسابات المعطّلة: authenticate() الجاهزة من Django
        # بترفض تسجيل دخول أي حساب is_active=False تلقائيًا بصمت (بترجّع None)
        # زي بالضبط لو الباسورد غلط — يعني موظفة إدخال معطّلة رح تشوف نفس
        # رسالة "بيانات خاطئة" حتى لو كاتبة باسوردها صح، وهذا مربك لها.
        # فبنتحقق يدويًا هون الأول: لو الحساب موجود، معطّل، والباسورد صحيح
        # فعليًا، منعرض رسالة واضحة "الحساب معطّل" بدل رسالة عامة مضلّلة.
        try:
            candidate = User.objects.get(username=username)
        except User.DoesNotExist:
            candidate = None

        if candidate is not None and not candidate.is_active and candidate.check_password(password):
            raise forms.ValidationError(
                "هذا الحساب معطّل حاليًا، تواصلي مع مديرة المدرسة",
                code="inactive",
            )

        self.user = authenticate(self.request, username=username, password=password)
        if self.user is None:
            # رسالة واحدة عامة لأي سبب فشل تاني (يوزر غلط، أو باسورد غلط،
            # أو حساب مو موجود) — عمدًا ما بنفرّق بينهم، عشان ما نسرّب
            # معلومة لأي حد يحاول يخمّن أسماء مستخدمين موجودة بالنظام.
            raise forms.ValidationError(
                "اسم المستخدم أو كلمة المرور غير صحيحة",
                code="invalid_login",
            )

        return cleaned_data

    def get_user(self):
        return self.user
    
class CreateAccountForm(forms.Form):
    """فورم موحّد لإنشاء حساب جديد — School Admin أو Data Entry، تختار الدور من داخل الفورم نفسه."""

    ROLE_CHOICES = [
        (UserRole.SCHOOL_ADMIN, "مديرة مدرسة"),
        (UserRole.DATA_ENTRY, "موظفة إدخال"),
    ]

    role = forms.ChoiceField(
        label="الدور",
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "app-input"}),
    )
    username = forms.CharField(
        label="اسم المستخدم",
        widget=forms.TextInput(attrs={"class": "app-input"}),
    )
    full_name = forms.CharField(
        label="الاسم الكامل",
        widget=forms.TextInput(attrs={"class": "app-input"}),
    )
    password1 = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={"class": "app-input"}),
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        widget=forms.PasswordInput(attrs={"class": "app-input"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("اسم المستخدم هذا مستخدم من قبل، اختاري اسم آخر")
        return username

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("كلمتا المرور غير متطابقتين")

        if password1:
            password_validation.validate_password(password1)

        return password2

    def save(self):
        return User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password1"],
            full_name=self.cleaned_data["full_name"],
            role=self.cleaned_data["role"],
        )