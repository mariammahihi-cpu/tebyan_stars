# rules/views.py

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import required_role, super_admin_required

from .forms import RuleForm, RuleValueForm
from .models import Rule


@required_role(UserRole.SCHOOL_ADMIN)
def manage_rules(request):
    if request.method == "POST":
        if request.user.role == UserRole.SCHOOL_ADMIN:
            raise PermissionDenied("إضافة قاعدة جديدة محصورة بمسؤولة النظام")

        form = RuleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة القاعدة بنجاح")
            return redirect("rules:manage_rules")
    else:
        form = RuleForm()

    return render(request, "rules/manage_rules.html", {
        "rules": Rule.objects.select_related("subject"),
        "form": form,
    })


@required_role(UserRole.SCHOOL_ADMIN)
def edit_rule(request, pk):
    rule = get_object_or_404(Rule, pk=pk)

    # Super Admin تعدّل القاعدة بكل تفاصيلها، School Admin تعدّل القيمة بس
    form_class = RuleForm if request.user.role == UserRole.SUPER_ADMIN else RuleValueForm

    if request.method == "POST":
        form = form_class(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, "تم التعديل بنجاح")
            return redirect("rules:manage_rules")
    else:
        form = form_class(instance=rule)

    return render(request, "rules/edit_rule.html", {"form": form, "object": rule})


@require_POST
@super_admin_required
def delete_rule(request, pk):
    rule = get_object_or_404(Rule, pk=pk)
    try:
        rule.delete()
        messages.success(request, "تم حذف القاعدة بنجاح")
    except ProtectedError:
        messages.error(
            request,
            "لا يمكن حذف هذه القاعدة لأنها مستخدمة بتقييمات موجودة",
        )
    return redirect("rules:manage_rules")