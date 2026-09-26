# leaderboard/services.py
#
# حساب ترتيب طلاب فصل معيّن — أكاديمي وسلوكي منفصلين تمامًا، أسبوعي
# وتراكمي — بالاعتماد على نفس مصدر الحقيقة الوحيد (Evaluation) المستخدم
# بكل حسابات الأرصدة بالنظام. استعلام تجميعي واحد لكل قائمة (مو استعلام
# لكل طالب)، عشان الصفحة تبقى خفيفة حتى لو كبر الفصل.

from django.db import models

from evaluations.models import Evaluation, WeeklyReset
from rules.models import RuleCategory
from students.models import Student


def _ranked_totals(section, *, category, week_start=None):
    qs = Evaluation.objects.filter(student__section=section, rule__category=category)
    if week_start:
        qs = qs.filter(created_at__gte=week_start)

    totals = dict(
        qs.values("student_id").annotate(total=models.Sum("value")).values_list("student_id", "total")
    )

    students = Student.objects.filter(section=section, is_active=True)
    ranked = [{"student": s, "value": totals.get(s.id, 0)} for s in students]
    ranked.sort(key=lambda row: row["value"], reverse=True)
    return ranked


def compute_leaderboard(section):
    """
    أربع قوائم مرتّبة تنازليًا لفصل معيّن: (أكاديمي/سلوك) × (أسبوعي/تراكمي).
    الأكاديمي = قواعد category="subject" فقط، السلوك = قواعد
    category="general" (الإشراف العام) فقط — بدون أي دمج بينهما، وبدون
    أثر قواعد الاستبدال (redemption) على أي منهما (تلك تمثّل "صرف رصيد"،
    مو أداء).
    """
    week_start = WeeklyReset.current_week_start()
    return {
        "weekly_academic": _ranked_totals(section, category=RuleCategory.SUBJECT, week_start=week_start),
        "weekly_behavior": _ranked_totals(section, category=RuleCategory.GENERAL, week_start=week_start),
        "cumulative_academic": _ranked_totals(section, category=RuleCategory.SUBJECT),
        "cumulative_behavior": _ranked_totals(section, category=RuleCategory.GENERAL),
    }