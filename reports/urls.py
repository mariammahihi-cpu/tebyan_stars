from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("parent/", views.parent_report_picker, name="parent_report_picker"),
    path("parent/<int:student_id>/", views.parent_report, name="parent_report"),
    path("parent/bulk/", views.bulk_parent_reports, name="bulk_parent_reports"),
    path("teacher/<int:teacher_id>/", views.teacher_report, name="teacher_report"),
    path("admin/", views.admin_report_filters, name="admin_report_filters"),
    path("admin/pdf/", views.admin_report_pdf, name="admin_report_pdf"),
]