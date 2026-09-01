from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("super-admin/", views.super_admin_dashboard, name="super_admin_dashboard"),
    path("school-admin/", views.school_admin_dashboard, name="school_admin_dashboard"),
    path("data-entry/", views.data_entry_dashboard, name="data_entry_dashboard"),

    path("accounts/", views.account_list, name="account_list"),
    path("accounts/new/", views.create_account, name="create_account"),
    path("accounts/data-entry/", views.data_entry_account_list, name="data_entry_account_list"),
    path("accounts/<int:user_id>/toggle/", views.toggle_account_active, name="toggle_account_active"),
]