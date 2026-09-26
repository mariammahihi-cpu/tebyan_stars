# reports/pdf.py

from urllib.parse import quote

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML


def static_file_uri(relative_path):
    """
    يرجّع مسار ملف مطلق بصيغة file:// لملف ستاتيك (خط أو صورة) — عشان
    WeasyPrint يضمّنه بالـPDF مباشرة من القرص وقت التوليد، بدون ما يعتمد
    على استضافة الملف عبر خادم HTTP (يشتغل بالتطوير والإنتاج بنفس الطريقة،
    وما يحتاج تشغيل السيرفر وقت توليد الملف). لو الملف غير موجود، ترجع
    نص فاضي بدل ما تكسر التوليد بالكامل.
    """
    absolute_path = finders.find(relative_path)
    return f"file://{absolute_path}" if absolute_path else ""


def render_pdf_bytes(template_name, context):
    """
    تحوّل قالب Django (HTML) لبايتات PDF خام (بدون تغليفها بـHttpResponse) —
    الأساس المشترك اللي يبني عليه render_pdf (تنزيل ملف واحد) والتصدير
    الجماعي (كل ملف يُضاف كعنصر داخل أرشيف ZIP).
    """
    html_string = render_to_string(template_name, context)
    return HTML(string=html_string).write_pdf()


def content_disposition_header(filename, fallback):
    """
    تبني قيمة ترويسة Content-Disposition بصيغة RFC 5987 (filename*=UTF-8''...)
    عشان تدعم أسماء ملفات عربية — ترويسات HTTP ما تقبل نصًا غير ASCII مباشرة،
    فنضيف اسمًا احتياطيًا بالإنجليزية (fallback) للمتصفحات القديمة جدًا.
    """
    encoded_filename = quote(filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded_filename}"


def render_pdf(template_name, context, filename):
    """
    تحوّل قالب Django (HTML) لملف PDF جاهز للتنزيل عبر WeasyPrint، وترجعه
    كـHttpResponse بترويسة تنزيل مباشر (attachment).
    """
    pdf_bytes = render_pdf_bytes(template_name, context)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(filename, "report.pdf")
    return response