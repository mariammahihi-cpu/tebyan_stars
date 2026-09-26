# rules/views.py

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import required_role, school_admin_required
from structure.models import Subject

from .forms import (
    GeneralRuleForm,
    RedemptionRuleEditForm,
    RedemptionRuleForm,
    RuleForm,
    RuleValueForm,
    SubjectRuleForm,
)
from .models import Rule, RuleCategory


@required_role(UserRole.SCHOOL_ADMIN)
def manage_rules(request):
    # نحسب is_deduction بايثونيًا (مو فلترة SQL على value) عشان تُحتسب صح
    # حتى لقواعد المدى (اللي value فيها فاضي أصلاً وإشارتها بـmin_value).
    rules = list(Rule.objects.all())
    add_count = sum(1 for r in rules if not r.is_deduction)
    deduct_count = sum(1 for r in rules if r.is_deduction)

    return render(request, "rules/manage_rules.html", {
        "add_count": add_count,
        "deduct_count": deduct_count,
        "total_count": len(rules),
    })


@required_role(UserRole.SCHOOL_ADMIN)
def rule_list(request, category):
    if category not in RuleCategory.values:
        raise Http404

    rules = Rule.objects.filter(category=category).select_related("subject").prefetch_related("grades")

    rule_type = request.GET.get("type", "")
    if rule_type == "add":
        rules = rules.filter(value__gt=0)
    elif rule_type == "deduct":
        rules = rules.filter(value__lt=0)

    subject_id = request.GET.get("subject", "") if category == RuleCategory.SUBJECT else ""
    if subject_id:
        rules = rules.filter(subject_id=subject_id)

    search = request.GET.get("q", "").strip()
    if search:
        rules = rules.filter(name__icontains=search)

    rules = rules.order_by("name")

    if category == RuleCategory.SUBJECT:
        form_class = SubjectRuleForm
    elif category == RuleCategory.REDEMPTION:
        form_class = RedemptionRuleForm
    else:
        form_class = GeneralRuleForm

    if request.method == "POST":
        # قواعد الاستبدال استثناء: صلاحية كاملة لمديرة المدرسة، بلا رجوع
        # لمسؤولة النظام — خلافًا لبقية التصنيفات.
        if request.user.role == UserRole.SCHOOL_ADMIN and category != RuleCategory.REDEMPTION:
            raise PermissionDenied("إضافة قاعدة جديدة محصورة بمسؤولة النظام")

        form = form_class(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة القاعدة بنجاح")
            return redirect("rules:rule_list", category=category)
    else:
        form = form_class()

    return render(request, "rules/rule_list.html", {
        "category": category,
        "category_label": RuleCategory(category).label,
        "rules": rules,
        "form": form,
        "rule_type": rule_type,
        "search": search,
        "subject_id": subject_id,
        "subjects": Subject.objects.all() if category == RuleCategory.SUBJECT else None,
    })


@required_role(UserRole.SCHOOL_ADMIN)
def edit_rule(request, pk):
    rule = get_object_or_404(Rule, pk=pk)

    # Super Admin تعدّل أي قاعدة بكل تفاصيلها. لقواعد الاستبدال تحديدًا،
    # School Admin كمان تعدّل بكل التفاصيل (استثناء صلاحية). لبقية
    # التصنيفات، School Admin تعدّل القيمة بس.
    if request.user.role == UserRole.SUPER_ADMIN:
        form_class = RuleForm
    elif rule.category == RuleCategory.REDEMPTION:
        form_class = RedemptionRuleEditForm
    else:
        form_class = RuleValueForm

    if request.method == "POST":
        form = form_class(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, "تم التعديل بنجاح")
            return redirect("rules:rule_list", category=rule.category)
    else:
        form = form_class(instance=rule)

    return render(request, "rules/edit_rule.html", {"form": form, "object": rule})


@require_POST
@school_admin_required
def delete_rule(request, pk):
    rule = get_object_or_404(Rule, pk=pk)

    # قواعد الاستبدال استثناء: صلاحية حذف كاملة لمديرة المدرسة. لبقية
    # التصنيفات، الحذف محصور بمسؤولة النظام.
    if request.user.role == UserRole.SCHOOL_ADMIN and rule.category != RuleCategory.REDEMPTION:
        raise PermissionDenied("حذف القواعد محصور بمسؤولة النظام، عدا قواعد الاستبدال")

    category = rule.category
    try:
        rule.delete()
        messages.success(request, "تم حذف القاعدة بنجاح")
    except ProtectedError:
        messages.error(
            request,
            "لا يمكن حذف هذه القاعدة لأنها مستخدمة بتقييمات موجودة",
        )
    return redirect("rules:rule_list", category=category)