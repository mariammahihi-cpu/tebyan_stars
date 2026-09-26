from django.urls import path

from . import views

app_name = "rules"

urlpatterns = [
    path("", views.manage_rules, name="manage_rules"),
    path("<str:category>/", views.rule_list, name="rule_list"),
    path("<int:pk>/edit/", views.edit_rule, name="edit_rule"),
    path("<int:pk>/delete/", views.delete_rule, name="delete_rule"),
]