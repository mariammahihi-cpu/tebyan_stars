# evaluations/urls.py

from django.urls import path

from . import views

app_name = "evaluations"

urlpatterns = [
    path("", views.apply_evaluation, name="apply_evaluation"),
    path("log/", views.activity_log, name="activity_log"),
    path("settings/", views.weekly_settings, name="weekly_settings"),
    path("settings/reset/", views.weekly_reset, name="weekly_reset"),
]