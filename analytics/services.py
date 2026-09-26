# analytics/services.py

from django.db.models import Count
from django.utils import timezone

from evaluations.models import Evaluation, WeeklyReset
from rules.models import RuleCategory
from structure.models import Section, SectionSubject, Subject
from students.models import Student

MAX_HEATMAP_WEEKS = 6
CONSECUTIVE_SILENT_WEEKS_ALERT = 2
FREQUENT_NEGATIVE_THRESHOLD = 3
ARCHIVE_PAGE_SIZE = 6
TOP_NEGATIVE_RULES_LIMIT = 5

# هندسة الرسم البياني الاتجاهي (SVG) — نفس الأبعاد لكل رسوم الاتجاه الثلاثة
# عشان تبقى متناسقة بصريًا جنب بعضها.
CHART_WIDTH = 320
CHART_MARGIN_X = 20
CHART_PLOT_TOP = 20
CHART_PLOT_BOTTOM = 90


def _week_periods():
    """
    يرجّع قايمة فترات (بداية، نهاية) للأسابيع المعروضة بالخريطة الحرارية،
    من الأقدم للأحدث — مبنية على آخر 6 أحداث تصفير أسبوعي (WeeklyReset)
    كحدود فاصلة، والفترة الأخيرة دايمًا مفتوحة (من آخر تصفير لحد الآن،
    الأسبوع الحالي الجاري). لو المدرسة ما سوّت تصفير أبدًا، ترجع فترة
    وحدة بس تغطي كل السجل التاريخي. عدد الفترات يتراوح 1-6 حسب المتوفر
    فعليًا من أحداث تصفير — بدون أي افتراض إنه لازم 6 دايمًا.
    """
    boundaries = list(
        WeeklyReset.objects.order_by("-performed_at").values_list("performed_at", flat=True)[:MAX_HEATMAP_WEEKS]
    )
    boundaries.reverse()

    now = timezone.now()
    if not boundaries:
        return [(None, now)]

    edges = boundaries + [now]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _period_index(created_at, periods):
    """يحدد أي فترة (رقم أسبوع) يقع فيها وقت تسجيل معيّن — مقارنة مباشرة، بلا استعلام إضافي."""
    last_index = len(periods) - 1
    for index, (start, end) in enumerate(periods):
        if start is not None and created_at < start:
            continue
        if index < last_index and created_at >= end:
            continue
        return index
    return None


def _all_week_periods():
    """
    نفس فكرة _week_periods بالضبط، بس بلا سقف الـ6 أسابيع — ترجّع كل
    الفترات منذ أول تصفير أسبوعي بتاريخ النظام، من الأقدم للأحدث. تُستخدم
    بصفحة الأرشيف بس (اللي تحتاج تصفّح كل التاريخ)، بعكس اللوحة الرئيسية
    اللي مقصود تبقى خفيفة وثابتة العرض (آخر 6 أسابيع دايمًا).
    """
    boundaries = list(WeeklyReset.objects.order_by("performed_at").values_list("performed_at", flat=True))

    now = timezone.now()
    if not boundaries:
        return [(None, now)]

    edges = boundaries + [now]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def compute_archive_page(page=0):
    """
    صفحة واحدة من أرشيف خريطة الالتزام — نفس فكرة الخريطة الحرارية باللوحة
    الرئيسية بالضبط (فصل × أسبوع)، بس بدل ما تتحدد بآخر 6 أسابيع ثابتة،
    تتصفّح كل تاريخ النظام صفحة صفحة (6 أسابيع بكل صفحة). page=0 يعني
    أحدث 6 أسابيع (نفس محتوى اللوحة الرئيسية بالضبط)، وكل رقم أعلى يرجع
    للخلف بالتاريخ أكثر.

    استعلام مجمّع واحد بس لكل صفحة (بغض النظر عن عدد الفصول) — نفس مبدأ
    الكفاءة المستخدم بكل حسابات هذا الملف.
    """
    all_periods = _all_week_periods()
    total_periods = len(all_periods)
    total_pages = max(1, -(-total_periods // ARCHIVE_PAGE_SIZE))  # سقف القسمة (ceiling division)
    page = max(0, min(page, total_pages - 1))

    end_index = total_periods - page * ARCHIVE_PAGE_SIZE
    start_index = max(0, end_index - ARCHIVE_PAGE_SIZE)
    periods = all_periods[start_index:end_index]

    sections = list(Section.objects.select_related("grade").all())

    applicable_subjects_by_section = {}
    for section_id, subject_id in SectionSubject.objects.values_list("section_id", "subject_id"):
        applicable_subjects_by_section.setdefault(section_id, set()).add(subject_id)

    lower_bound, _ = periods[0]
    _, upper_bound = periods[-1]

    evaluations_qs = Evaluation.objects.filter(subject__isnull=False, created_at__lt=upper_bound)
    if lower_bound is not None:
        evaluations_qs = evaluations_qs.filter(created_at__gte=lower_bound)

    # الاستعلام المجمّع الوحيد لهذي الصفحة — يجيب بس الأعمدة اللازمة لحساب
    # نسبة التغطية (فصل × مادة × أسبوع)، بلا أي عمود إضافي ما نحتاجه هنا.
    rows = evaluations_qs.values_list("student__section_id", "subject_id", "created_at")

    covered_subjects = {}  # (week_index, section_id) -> set(subject_id) مُقيَّمة
    for section_id, subject_id, created_at in rows:
        week_index = _period_index(created_at, periods)
        if week_index is None:
            continue
        covered_subjects.setdefault((week_index, section_id), set()).add(subject_id)

    is_current_page = page == 0
    global_current_index = total_periods - 1

    week_labels = []
    for offset, (start, end) in enumerate(periods):
        global_index = start_index + offset
        if global_index == global_current_index and is_current_page:
            week_labels.append("الحالي")
        else:
            week_labels.append(start.strftime("%Y-%m-%d") if start else "—")

    heatmap_rows = []
    for section in sections:
        applicable = applicable_subjects_by_section.get(section.id, set())
        cells = []
        for week_index in range(len(periods)):
            if not applicable:
                cells.append({"percent": None})
                continue
            covered = covered_subjects.get((week_index, section.id), set()) & applicable
            cells.append({"percent": round(100 * len(covered) / len(applicable))})
        heatmap_rows.append({"section": section, "cells": cells})

    return {
        "heatmap_rows": heatmap_rows,
        "week_labels": week_labels,
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages - 1,  # صفحة أقدم بالتاريخ
        "has_previous": page > 0,  # صفحة أحدث بالتاريخ
        "range_start": all_periods[start_index][0],
        "range_end": all_periods[end_index - 1][1],
    }


def _trend_chart_points(values):
    """
    يحوّل قايمة قيم أسبوعية (وممكن يكون فيها None لأسبوع بلا بيانات) لإحداثيات
    SVG جاهزة للرسم، ويرجّعها مقسّمة لقطع متتالية (segments) — عشان ما نرسم
    خط وهمي يعبر فوق أسبوع بلا أي بيانات إطلاقًا. التحجيم بيتحدد بدالة
    to_y اللي يمررها المستدعي (فرق بين مقياس نسبة مئوية ثابت 0-100 ومقياس
    متماثل حول الصفر للمتوسطات اللي ممكن تكون سالبة).
    """
    count = len(values)
    spacing = (CHART_WIDTH - 2 * CHART_MARGIN_X) / (count - 1) if count > 1 else 0

    points = []
    for index, value in enumerate(values):
        x = CHART_MARGIN_X + index * spacing if count > 1 else CHART_WIDTH / 2
        points.append({"x": round(x, 1), "value": value, "has_value": value is not None})

    return points


def _build_trend_chart(title, color, week_labels, values, is_percent):
    """
    يبني بيانات رسم اتجاهي واحد (رسم صغير مستقل بمقياسه الخاص — بدون محور
    مشترك مع الرسوم الثانية، تجنّبًا لرسم بمحورين). كل الهندسة (إحداثيات
    x/y، قطع الخط المتصلة) تُحسب هنا بايثون، والقالب يرسمها بس.
    """
    points = _trend_chart_points(values)

    if is_percent:
        def to_y(value):
            return CHART_PLOT_BOTTOM - (value / 100) * (CHART_PLOT_BOTTOM - CHART_PLOT_TOP)
        zero_y = None
    else:
        max_abs = max((abs(v) for v in values if v is not None), default=0) or 1
        mid_y = (CHART_PLOT_TOP + CHART_PLOT_BOTTOM) / 2

        def to_y(value):
            return mid_y - (value / max_abs) * (mid_y - CHART_PLOT_TOP)
        zero_y = round(mid_y, 1)

    for index, point in enumerate(points):
        point["y"] = round(to_y(point["value"]), 1) if point["has_value"] else None
        point["week_label"] = week_labels[index]

    segments = []
    current_segment = []
    for point in points:
        if point["has_value"]:
            current_segment.append(point)
        else:
            if current_segment:
                segments.append(current_segment)
            current_segment = []
    if current_segment:
        segments.append(current_segment)

    path_segments = [" ".join(f"{p['x']},{p['y']}" for p in segment) for segment in segments]
    last_value = next((v for v in reversed(values) if v is not None), None)

    return {
        "title": title,
        "color": color,
        "is_percent": is_percent,
        "points": points,
        "path_segments": path_segments,
        "zero_y": zero_y,
        "last_value": last_value,
        "has_data": any(v is not None for v in values),
    }


def _top_negative_rules(week_start):
    """
    أعلى القواعد السلبية (خصم) تكرارًا هذا الأسبوع على مستوى المدرسة كاملة
    — بجميع الأنواع (أكاديمية وسلوكية) معًا. استعلام مجمّع بسيط واحد:
    Group By على القاعدة + Count + ترتيب تنازلي.
    """
    qs = Evaluation.objects.filter(value__lt=0)
    if week_start:
        qs = qs.filter(created_at__gte=week_start)
    return list(
        qs.values("rule_id", "rule__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:TOP_NEGATIVE_RULES_LIMIT]
    )


def _top_deduction_section(week_start, category):
    """
    الفصل الأعلى بعدد قواعد الخصم من تصنيف معيّن (مادة أو إشراف عام) هذا
    الأسبوع — استعلام مجمّع بسيط: Group By على الفصل + Count + ترتيب
    تنازلي، مع أخذ أول نتيجة بس. ترجع None لو ما فيه أي قاعدة خصم من هذا
    التصنيف مطبّقة هذا الأسبوع.
    """
    qs = Evaluation.objects.filter(value__lt=0, rule__category=category)
    if week_start:
        qs = qs.filter(created_at__gte=week_start)
    top = (
        qs.values("student__section_id")
        .annotate(count=Count("id"))
        .order_by("-count")
        .first()
    )
    if not top:
        return None
    section = Section.objects.select_related("grade").get(pk=top["student__section_id"])
    return {"section": section, "count": top["count"]}


def compute_dashboard_analytics():
    """
    يبني كل بيانات لوحة التحليلات — المؤشرات العامة وخريطة التغطية
    الحرارية — من استعلام واحد مجمّع على جدول Evaluation يغطي كامل نافذة
    الأسابيع المعروضة، بدل استعلام منفصل لكل خلية بالخريطة (كان سيصير
    عدد_الفصول × عدد_الأسابيع استعلام لو حسبنا كل خلية لحالها). كل
    التصنيف والتجميع بعد هالاستعلام يصير بالذاكرة على نفس الصفوف.
    """
    sections = list(Section.objects.select_related("grade").all())

    applicable_subjects_by_section = {}
    for section_id, subject_id in SectionSubject.objects.values_list("section_id", "subject_id"):
        applicable_subjects_by_section.setdefault(section_id, set()).add(subject_id)

    periods = _week_periods()
    current_week_index = len(periods) - 1
    lower_bound = periods[0][0]

    evaluations_qs = Evaluation.objects.all()
    if lower_bound is not None:
        evaluations_qs = evaluations_qs.filter(created_at__gte=lower_bound)

    # الاستعلام المجمّع الوحيد: يجيب كل الأعمدة اللازمة لكل حسابات الصفحة
    # (المؤشرات، الخريطة الحرارية، مقارنة المواد، وقائمة المتابعة الفردية)
    # بضربة وحدة — لا استعلام إضافي لكل خلية أو فصل أو طالب، بغض النظر عن
    # عدد الفصول/الأسابيع/الطلاب المعروضين.
    rows = evaluations_qs.values_list(
        "student_id", "student__section_id", "subject_id", "created_at", "value", "rule__category"
    )

    covered_subjects = {}  # (week_index, section_id) -> set(subject_id) مُقيَّمة
    active_sections_by_week = {index: set() for index in range(len(periods))}  # أي نشاط إطلاقًا (مادة أو إشراف)
    subject_values_by_week = {index: [] for index in range(len(periods))}  # كل قيم تقييمات المواد، أسبوعًا بأسبوع — للاتجاه الزمني
    general_values_by_week = {index: [] for index in range(len(periods))}  # كل قيم تقييمات الإشراف، أسبوعًا بأسبوع — للاتجاه الزمني
    current_week_values_by_subject = {}  # subject_id -> [قيم تقييماته هذا الأسبوع] — لمقارنة المواد
    student_week_values = {}  # (week_index, student_id) -> [قيم تقييماته بذاك الأسبوع] — لقائمة المتابعة الفردية

    for student_id, section_id, subject_id, created_at, value, category in rows:
        week_index = _period_index(created_at, periods)
        if week_index is None:
            continue

        active_sections_by_week[week_index].add(section_id)
        student_week_values.setdefault((week_index, student_id), []).append(value)

        if subject_id is not None:
            covered_subjects.setdefault((week_index, section_id), set()).add(subject_id)

        if category == RuleCategory.SUBJECT:
            subject_values_by_week[week_index].append(value)
            if week_index == current_week_index:
                current_week_values_by_subject.setdefault(subject_id, []).append(value)
        elif category == RuleCategory.GENERAL:
            general_values_by_week[week_index].append(value)

    current_week_subject_values = subject_values_by_week[current_week_index]
    current_week_general_values = general_values_by_week[current_week_index]

    # ---- 1) متوسط الأداء الأكاديمي (تقييمات المواد هذا الأسبوع) ----
    academic_average = (
        round(sum(current_week_subject_values) / len(current_week_subject_values), 2)
        if current_week_subject_values else None
    )

    # ---- 2) متوسط السلوك العام (تقييمات الإشراف هذا الأسبوع) ----
    behavior_average = (
        round(sum(current_week_general_values) / len(current_week_general_values), 2)
        if current_week_general_values else None
    )

    # ---- 3) نسبة التزام التقييم الإجمالية (كل فصل×مادة) — لكل أسبوع معروض ----
    # نحسبها لكل الأسابيع دفعة وحدة (مو بس الحالي) عشان نعيد استخدام نفس
    # القيم لاحقًا بالرسم الاتجاهي الزمني، بدل حساب منفصل هناك.
    total_applicable_pairs = sum(len(subjects) for subjects in applicable_subjects_by_section.values())
    coverage_percent_by_week = {}
    for week_index in range(len(periods)):
        covered_pairs = sum(
            len(covered_subjects.get((week_index, section_id), set()) & subjects)
            for section_id, subjects in applicable_subjects_by_section.items()
        )
        coverage_percent_by_week[week_index] = (
            round(100 * covered_pairs / total_applicable_pairs) if total_applicable_pairs else None
        )
    overall_coverage_percent = coverage_percent_by_week[current_week_index] or 0

    # ---- 4) عدد الفصول اللي تجاوزت أسبوعين متتاليين بدون أي تقييم ----
    # من آخر أسبوع للخلف (شامل الأسبوع الحالي الجاري لو لسا بلا أي نشاط)
    # نحسب أطول سلسلة متتالية بلا أي نشاط — لو وصلت أسبوعين أو أكثر،
    # الفصل يُحتسب ضمن هذا التنبيه.
    silent_sections_count = 0
    for section in sections:
        streak = 0
        for week_index in range(current_week_index, -1, -1):
            if section.id in active_sections_by_week[week_index]:
                break
            streak += 1
        if streak >= CONSECUTIVE_SILENT_WEEKS_ALERT:
            silent_sections_count += 1

    # ---- خريطة التزام الفصول الحرارية (فصل × أسبوع) ----
    heatmap_rows = []
    for section in sections:
        applicable = applicable_subjects_by_section.get(section.id, set())
        cells = []
        for week_index in range(len(periods)):
            if not applicable:
                cells.append({"percent": None, "is_current": week_index == current_week_index})
                continue
            covered = covered_subjects.get((week_index, section.id), set()) & applicable
            percent = round(100 * len(covered) / len(applicable))
            cells.append({"percent": percent, "is_current": week_index == current_week_index})
        heatmap_rows.append({"section": section, "cells": cells})

    week_labels = []
    short_week_labels = []  # نسخة مختصرة (شهر-يوم) للاستخدام كمحور سيني بالرسم الاتجاهي الضيّق
    for week_index, (start, end) in enumerate(periods):
        if week_index == current_week_index:
            week_labels.append("الحالي")
            short_week_labels.append("الحالي")
        else:
            week_labels.append(start.strftime("%Y-%m-%d") if start else "—")
            short_week_labels.append(start.strftime("%m-%d") if start else "—")

    # ---- مقارنة أداء المواد (الأسبوع الحالي) ----
    # مبنية بالكامل من نفس الصفوف اللي جبناها فوق لخريطة التغطية — صفر
    # استعلامات إضافية غير جلب قايمة المواد نفسها (استعلام صغير واحد).
    sections_by_subject = {}
    for section_id, subjects in applicable_subjects_by_section.items():
        for subject_id in subjects:
            sections_by_subject.setdefault(subject_id, set()).add(section_id)

    covered_sections_by_subject_this_week = {}
    for (week_index, section_id), subjects in covered_subjects.items():
        if week_index != current_week_index:
            continue
        for subject_id in subjects:
            covered_sections_by_subject_this_week.setdefault(subject_id, set()).add(section_id)

    subject_comparison = []
    for subject in Subject.objects.all():
        values = current_week_values_by_subject.get(subject.id, [])
        average = round(sum(values) / len(values), 2) if values else None

        assigned_sections = sections_by_subject.get(subject.id, set())
        covered_sections = covered_sections_by_subject_this_week.get(subject.id, set()) & assigned_sections
        coverage_percent = (
            round(100 * len(covered_sections) / len(assigned_sections)) if assigned_sections else None
        )

        subject_comparison.append({
            "subject": subject,
            "average": average,
            "evaluations_count": len(values),
            "positive_count": sum(1 for v in values if v > 0),
            "negative_count": sum(1 for v in values if v < 0),
            "coverage_percent": coverage_percent,
        })

    # ترتيب تنازلي بمتوسط الأداء — المواد بلا أي تقييم هذا الأسبوع بالآخر
    subject_comparison.sort(key=lambda row: (row["average"] is None, -(row["average"] or 0)))

    # نسبة عرض كل شريط بالرسم المتفرّع (diverging bar) كنسبة من أعلى قيمة
    # مطلقة بين كل المواد — عشان الأشرطة تكون قابلة للمقارنة البصرية بمقياس
    # واحد مشترك، بدل ما يكون كل شريط بمقياسه الخاص.
    max_abs_average = max(
        (abs(row["average"]) for row in subject_comparison if row["average"] is not None),
        default=0,
    )
    for row in subject_comparison:
        row["bar_percent"] = (
            round(50 * abs(row["average"]) / max_abs_average) if row["average"] and max_abs_average else 0
        )

    # ---- قائمة الطلاب المحتاجين متابعة فردية ----
    # ثلاث علامات مستقلة، أي وحدة منها كافية لإدراج الطالب — مبنية بالكامل
    # من نفس student_week_values اللي جمّعناها بالحلقة فوق (صفر استعلامات
    # إضافية غير جلب قايمة الطالبات النشيطات نفسها):
    # 1) رصيد هذا الأسبوع سالب.
    # 2) رصيد هذا الأسبوع أقل من رصيد الأسبوع السابق (اتجاه متراجع).
    # 3) عدد التقييمات السالبة هذا الأسبوع >= 3 (تكرار، حتى لو الرصيد
    #    الإجمالي لسه موجب بسبب إضافات عوّضت عليه).
    previous_week_index = current_week_index - 1 if current_week_index >= 1 else None

    watchlist = []
    for student in Student.objects.filter(is_active=True).select_related("section"):
        current_values = student_week_values.get((current_week_index, student.id), [])
        current_total = sum(current_values)
        negative_count = sum(1 for v in current_values if v < 0)

        reasons = []
        if current_values and current_total < 0:
            reasons.append("رصيد سالب هذا الأسبوع")
        if previous_week_index is not None and current_values:
            previous_total = sum(student_week_values.get((previous_week_index, student.id), []))
            if current_total < previous_total:
                reasons.append("أداء متراجع مقارنة بالأسبوع السابق")
        if negative_count >= FREQUENT_NEGATIVE_THRESHOLD:
            reasons.append(f"{negative_count} تقييمات سالبة هذا الأسبوع")

        if reasons:
            watchlist.append({
                "student": student,
                "weekly_total": current_total,
                "reasons": reasons,
            })

    # الأكثر إلحاحًا أولاً: عدد العلامات المُفعّلة تنازليًا، وبالتساوي
    # الرصيد الأسوأ أولاً.
    watchlist.sort(key=lambda row: (-len(row["reasons"]), row["weekly_total"]))

    # ---- الرسم البياني الاتجاهي الزمني ----
    # ثلاثة رسوم صغيرة مستقلة (small multiples) — مو رسم واحد بمحورين،
    # لأن المتوسطات (قطبية، ممكن سالبة) ونسبة الالتزام (0-100٪ ثابتة)
    # مقياسان مختلفان تمامًا. كلها مبنية من نفس subject_values_by_week
    # وgeneral_values_by_week وcoverage_percent_by_week المحسوبة فوق —
    # صفر استعلامات إضافية.
    academic_values_by_week = [
        round(sum(subject_values_by_week[i]) / len(subject_values_by_week[i]), 2)
        if subject_values_by_week[i] else None
        for i in range(len(periods))
    ]
    behavior_values_by_week = [
        round(sum(general_values_by_week[i]) / len(general_values_by_week[i]), 2)
        if general_values_by_week[i] else None
        for i in range(len(periods))
    ]
    coverage_values_by_week = [coverage_percent_by_week[i] for i in range(len(periods))]

    trend_charts = [
        _build_trend_chart("متوسط الأداء الأكاديمي", "#1B5E20", short_week_labels, academic_values_by_week, is_percent=False),
        _build_trend_chart("متوسط السلوك العام", "#F9A825", short_week_labels, behavior_values_by_week, is_percent=False),
        _build_trend_chart("نسبة الالتزام الإجمالية", "#66BB6A", short_week_labels, coverage_values_by_week, is_percent=True),
    ]

    # ---- بطاقات تشخيصية: الأكثر تكرارًا من القواعد السلبية هذا الأسبوع ----
    # كل بطاقة باستعلام مجمّع بسيط ومستقل (Group By + Count + Order By)
    # مباشرة على Evaluation.value < 0 — بدون إعادة استخدام أي حسابات فوق.
    week_start = WeeklyReset.current_week_start()
    top_negative_rules = _top_negative_rules(week_start)
    top_general_deduction_section = _top_deduction_section(week_start, RuleCategory.GENERAL)
    top_subject_deduction_section = _top_deduction_section(week_start, RuleCategory.SUBJECT)

    return {
        "academic_average": academic_average,
        "behavior_average": behavior_average,
        "overall_coverage_percent": overall_coverage_percent,
        "silent_sections_count": silent_sections_count,
        "heatmap_rows": heatmap_rows,
        "week_labels": week_labels,
        "subject_comparison": subject_comparison,
        "watchlist": watchlist,
        "frequent_negative_threshold": FREQUENT_NEGATIVE_THRESHOLD,
        "trend_charts": trend_charts,
        "trend_week_count": len(periods),
        "top_negative_rules": top_negative_rules,
        "top_general_deduction_section": top_general_deduction_section,
        "top_subject_deduction_section": top_subject_deduction_section,
    }