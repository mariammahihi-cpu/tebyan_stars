# analytics/views.py

from django.shortcuts import render

from accounts.permissions import school_admin_required

from .services import compute_archive_page, compute_dashboard_analytics


@school_admin_required
def dashboard(request):
    """
    لوحة تحليلات المديرة — المرحلة الأولى: مؤشرات عامة على مستوى المدرسة
    (أداء أكاديمي، سلوك عام، التزام إجمالي، فصول متعثرة) + خريطة حرارية
    لالتزام الفصول بالتقييم عبر آخر 6 أسابيع. محصورة بالمديرة والمسؤولة،
    بنفس نمط تقرير المديرة.
    """
    context = compute_dashboard_analytics()
    return render(request, "analytics/dashboard.html", context)


@school_admin_required
def archive(request):
    """
    أرشيف خريطة الالتزام — تصفّح كل الأسابيع منذ بداية استخدام النظام،
    صفحة كل 6 أسابيع (نفس حجم عرض خريطة اللوحة الرئيسية)، بعكس اللوحة
    الرئيسية اللي مقصود تبقى ثابتة العرض (آخر 6 أسابيع بس دايمًا).
    """
    try:
        page = int(request.GET.get("page", 0))
    except ValueError:
        page = 0

    context = compute_archive_page(page)
    return render(request, "analytics/archive.html", context)