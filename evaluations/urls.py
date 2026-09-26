# evaluations/urls.py

from django.urls import path

from . import views

app_name = "evaluations"

urlpatterns = [
    path("", views.apply_evaluation, name="apply_evaluation"),
    path("bulk-table/", views.bulk_table, name="bulk_table"),
    path("bulk-toggle/", views.bulk_toggle, name="bulk_toggle"),
    path("bulk-apply-many/", views.bulk_apply_many, name="bulk_apply_many"),
    path("bulk-restore/", views.bulk_restore, name="bulk_restore"),
    path("log/", views.activity_log, name="activity_log"),
    path("trader/", views.pos_manage, name="pos_manage"),
    path("settings/", views.weekly_settings, name="weekly_settings"),
    path("settings/reset/", views.weekly_reset, name="weekly_reset"),
]