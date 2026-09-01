from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.db.models import Q

from .forms import CreateAccountForm, LoginForm
from .models import User, UserRole
from .permissions import (
    data_entry_required,
    required_role,
    school_admin_required,
    super_admin_required,
)

def _dashboard_url_name(user):
    """يرجّع اسم مسار (URL name) لوحة التحكم المناسبة لدور المستخدم."""
    if user.role == UserRole.SUPER_ADMIN:
        return "accounts:super_admin_dashboard"
    if user.role == UserRole.SCHOOL_ADMIN:
        return "accounts:school_admin_dashboard"
    return "accounts:data_entry_dashboard"


def login_view(request):
    # إذا مسجلة دخول أصلاً، ما فيه داعي تشوف فورم تسجيل الدخول من جديد
    if request.user.is_authenticated:
        return redirect(_dashboard_url_name(request.user))

    if request.method == "POST":
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)

            # لو المستخدمة كانت رايحة لصفحة محمية معينة وتم رجّعها لتسجيل
            # الدخول (عبر required_role بملف permissions.py)، بعد نجاح
            # الدخول نرجّعها لنفس الصفحة اللي كانت طالباها، مو للوحة العامة.
            next_url = request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect(_dashboard_url_name(user))
    else:
        form = LoginForm(request=request)

    return render(request, "accounts/login.html", {
        "form": form,
        "next": request.POST.get("next", request.GET.get("next", "")),
    })


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("accounts:login")


@super_admin_required
def super_admin_dashboard(request):
    # صفحة مؤقتة بسيطة — رح تنستبدل بلوحة تحكم حقيقية لما نبني بقية الـ apps
    return render(request, "accounts/dashboard_placeholder.html", {
        "title": "لوحة مسؤولة النظام",
    })


@school_admin_required
def school_admin_dashboard(request):
    return render(request, "accounts/dashboard_placeholder.html", {
        "title": "لوحة مديرة المدرسة",
    })


@data_entry_required
def data_entry_dashboard(request):
    return render(request, "accounts/dashboard_placeholder.html", {
        "title": "واجهة إدخال البيانات",
    })

@super_admin_required
def account_list(request):
    """قائمة كل الحسابات ما عدا حسابات Super Admin (مالهاش داعي تدار من هون)."""
    accounts = User.objects.exclude(role=UserRole.SUPER_ADMIN).order_by("role", "full_name")
    return render(request, "accounts/account_list.html", {"accounts": accounts})


@super_admin_required
def create_account(request):
    if request.method == "POST":
        form = CreateAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(request, f"تم إنشاء حساب {account.full_name} بنجاح")
            return redirect("accounts:account_list")
    else:
        form = CreateAccountForm()

    return render(request, "accounts/create_account.html", {"form": form})


@school_admin_required
def data_entry_account_list(request):
    """قائمة موظفات الإدخال بس — هاي شاشة School Admin اليومية لتفعيل/تعطيل الحسابات."""
    accounts = User.objects.filter(role=UserRole.DATA_ENTRY).order_by("full_name")
    return render(request, "accounts/data_entry_account_list.html", {"accounts": accounts})


@require_POST
@required_role(UserRole.SCHOOL_ADMIN)
def toggle_account_active(request, user_id):
    """
    تبديل حالة تفعيل حساب. Super Admin بتوصلها تلقائيًا (معفاة من فحص الدور
    بـ required_role)، وSchool Admin بتوصلها بس — لكن مقيّدة هون داخل الجسم
    بقاعدة عمل: ما تقدر تلمس إلا حسابات Data Entry.
    """
    target = get_object_or_404(User, pk=user_id)

    if request.user.role == UserRole.SCHOOL_ADMIN and target.role != UserRole.DATA_ENTRY:
        raise PermissionDenied("تقدرين تفعّلي أو تعطّلي حسابات موظفات الإدخال بس")

    if target.pk == request.user.pk:
        raise PermissionDenied("ما تقدري تعطّلي حسابك انتِ")

    target.is_active = not target.is_active
    target.save()

    messages.success(
        request,
        f"تم {'تفعيل' if target.is_active else 'تعطيل'} حساب {target.full_name}",
    )

    if request.user.role == UserRole.SCHOOL_ADMIN:
        return redirect("accounts:data_entry_account_list")
    return redirect("accounts:account_list")

@super_admin_required
def account_list(request):
    accounts = User.objects.exclude(role=UserRole.SUPER_ADMIN)

    query = request.GET.get("q", "").strip()
    if query:
        accounts = accounts.filter(
            Q(full_name__icontains=query) | Q(username__icontains=query)
        )

    role_filter = request.GET.get("role", "")
    if role_filter:
        accounts = accounts.filter(role=role_filter)

    accounts = accounts.order_by("role", "full_name")

    return render(request, "accounts/account_list.html", {
        "accounts": accounts,
        "search": query,
        "role_filter": role_filter,
        "role_choices": [
            (UserRole.SCHOOL_ADMIN, "مديرة مدرسة"),
            (UserRole.DATA_ENTRY, "موظفة إدخال"),
        ],
    })


@school_admin_required
def data_entry_account_list(request):
    accounts = User.objects.filter(role=UserRole.DATA_ENTRY)

    query = request.GET.get("q", "").strip()
    if query:
        accounts = accounts.filter(
            Q(full_name__icontains=query) | Q(username__icontains=query)
        )

    accounts = accounts.order_by("full_name")

    return render(request, "accounts/data_entry_account_list.html", {
        "accounts": accounts,
        "search": query,
    })