# reports/services.py

from django.db.models import Sum

from evaluations.models import Evaluation, WeeklyReset


def compute_performance_trend(student, *, subject=None):
    """
    تقارن مجموع رصيد الطالب بآخر فترتين أسبوعيتين حسب سجل التصفير
    (WeeklyReset) — "تحسّن" لو المجموع الحالي أعلى من السابق، "تراجع" لو
    أقل، "مستقر" لو متساوٍ. تمرير subject يقصر المقارنة على مادة واحدة
    بعينها (لتقرير المعلّمة، حتى ما يختلط أداؤها بمواد معلّمات أخريات)؛
    بدونه تُحسب على كل الفئات مجتمعة (لتقرير ولي الأمر). تحتاج فترتين
    مكتملتين على الأقل (يعني تصفيرين مسجّلين على الأقل بالتاريخ) عشان
    تكون المقارنة ذات معنى؛ لو ما توفرت، ترجع None (يعني "غير متاح بعد").
    """
    resets = list(WeeklyReset.objects.order_by("-performed_at")[:2])
    if len(resets) < 2:
        return None

    current_start = resets[0].performed_at
    previous_start = resets[1].performed_at
    previous_end = resets[0].performed_at

    qs = Evaluation.objects.filter(student=student)
    if subject is not None:
        qs = qs.filter(subject=subject)

    current_total = qs.filter(created_at__gte=current_start).aggregate(
        total=Sum("value")
    )["total"] or 0

    previous_total = qs.filter(
        created_at__gte=previous_start, created_at__lt=previous_end
    ).aggregate(total=Sum("value"))["total"] or 0

    if current_total > previous_total:
        return "improved"
    if current_total < previous_total:
        return "declined"
    return "stable"