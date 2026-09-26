# evaluations/services.py

from django.core.exceptions import ValidationError
from django.db import transaction

from students.models import Student

from .models import Evaluation, POSTransaction


class POSService:
    """
    منطق تنفيذ تحويلات "تاجر التبيان" الفعلي والآمن. الفحص المبكر الودود
    موجود بـ POSTransactionForm.clean() (بدون قفل، فقط لإظهار رسالة خطأ
    سريعة بالواجهة)، لكن هذا هو المكان الوحيد اللي فيه الفحص النهائي
    الآمن ضد race conditions — راجعي شرح القيد الذري بالأسفل.
    """

    @staticmethod
    @transaction.atomic
    def transfer(*, buyer_id, seller_id, amount, recorded_by):
        """
        تحويل amount من رصيد seller التراكمي إلى buyer، كعملية واحدة ذرية.

        القفل (select_for_update): بما إن الرصيد التراكمي محسوب Live من
        SUM على Evaluation + POSTransaction (بدون أي حقل رصيد مخزَّن)،
        قراءة الرصيد وحدها بدون قفل تسمح بسباق: موظفتان تفتحان تحويلًا
        لنفس الطرف بنفس اللحظة، كل وحدة تقرأ نفس الرصيد القديم قبل ما
        تُحفظ عملية الثانية، فيوافق الفحص مرتين رغم إن الرصيد يكفي مرة
        وحدة بس. select_for_update() يقفل صف الطرفين بقاعدة البيانات
        وقت القراءة داخل نفس المعاملة — أي معاملة ثانية تحاول قفل نفس
        الصف تنتظر (blocking) لحد ما الأولى تُنجز (commit) أو تتراجع
        (rollback)، فتقرأ الرصيد المحدَّث فعليًا، مو رقم قديم.

        ترتيب القفل (sorted بالـ id): لتفادي deadlock لو صار تحويلان
        متعاكسان بنفس اللحظة (الطرف أ يُحوِّل لِـ ب، وبنفس اللحظة ب
        يُحوِّل لِـ أ) — لو كل معاملة تقفل بترتيب مختلف، ممكن توصل الاثنتين
        لحالة انتظار متبادل دائم. القفل بترتيب ثابت (الأصغر id أولًا)
        يضمن إن كل المعاملات تتنافس على نفس الترتيب، فما يصير انتظار دائري.

        @transaction.atomic: يضمن إن فحص الرصيد (بعد القفل) وإنشاء صف
        POSTransaction يصيران كوحدة واحدة — لو صار استثناء (مثلاً
        ValidationError لعدم كفاية الرصيد) بعد بدء المعاملة، Django يسوي
        rollback كامل تلقائيًا، فما يصير أي أثر جزئي بقاعدة البيانات.
        """
        if buyer_id == seller_id:
            raise ValidationError("لا يمكن التحويل لنفس الطرف.")

        locked = {
            s.id: s
            for s in Student.objects.select_for_update().filter(
                id__in=sorted([buyer_id, seller_id])
            )
        }
        buyer = locked.get(buyer_id)
        seller = locked.get(seller_id)
        if buyer is None or seller is None:
            raise ValidationError("الطرف المحدَّد غير موجود.")

        seller_balance = Evaluation.cumulative_total(seller)
        if seller_balance < amount:
            raise ValidationError(
                f"لا يوجد رصيد كافٍ لدى الطرف المُحوِّل. الرصيد الحالي: {seller_balance} نجمة."
            )

        return POSTransaction.objects.create(
            buyer=buyer,
            seller=seller,
            amount=amount,
            recorded_by=recorded_by,
        )
