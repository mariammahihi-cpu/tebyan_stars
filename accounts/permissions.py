# accounts/permissions.py

"""
ديكوريتورز (decorators) لحماية الـ views حسب دور المستخدم (role-based access control).

هذا الملف بديل كامل لنظام Django's Groups/Permissions الجاهز — لأنه موديل
User عندنا ما بيستخدمه أصلاً (راجعي شرح models.py). كل التحقق من الصلاحيات
بيصير هون، بالاعتماد على حقل `role` بس.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import UserRole


def required_role(*allowed_roles):
    """
    Decorator factory بتتأكد إن المستخدم:
    1. مسجل دخول (وإلا بترجعه لصفحة تسجيل الدخول تلقائيًا).
    2. دوره ضمن allowed_roles (وإلا بترفع PermissionDenied → صفحة 403).

    Super Admin مستثنى دايمًا من هذا الشرط ويعدي أي فحص دور، لأنه حسب
    قواعد العمل عنده "وصول لكل شيء" بالنظام — مو بس الأدوار المذكورة صراحة.

    الاستخدام:
        @required_role(UserRole.SCHOOL_ADMIN)
        def weekly_reset_view(request):
            ...

        @required_role(UserRole.SCHOOL_ADMIN, UserRole.DATA_ENTRY)
        def some_shared_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url="accounts:login")
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role == UserRole.SUPER_ADMIN:
                return view_func(request, *args, **kwargs)

            if request.user.role not in allowed_roles:
                raise PermissionDenied("لا تملكين صلاحية الوصول إلى هذه الصفحة")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


# اختصارات جاهزة للاستخدام المباشر بالـ views، بدل ما نكرر required_role(UserRole.X) بكل مكان

super_admin_required = required_role(UserRole.SUPER_ADMIN)
school_admin_required = required_role(UserRole.SCHOOL_ADMIN)
data_entry_required = required_role(UserRole.DATA_ENTRY)