from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("sections/<int:section_id>/", views.classroom_roster, name="classroom_roster"),
    path("sections/<int:section_id>/quick-add/", views.quick_add_student, name="quick_add_student"),
    path("<int:student_id>/edit-ajax/", views.edit_student_ajax, name="edit_student_ajax"),
    path("<int:student_id>/toggle-ajax/", views.toggle_student_active_ajax, name="toggle_student_active_ajax"),
]