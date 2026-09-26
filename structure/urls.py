from django.urls import path

from . import views

app_name = "structure"

urlpatterns = [
    path("grades/", views.grade_list, name="grade_list"),
    path("grades/<int:grade_id>/sections/", views.section_list, name="section_list"),
    path("grades/<int:pk>/edit/", views.edit_grade, name="edit_grade"),
    path("grades/<int:pk>/delete/", views.delete_grade, name="delete_grade"),

    path("sections/<int:pk>/edit/", views.edit_section, name="edit_section"),
    path("sections/<int:pk>/delete/", views.delete_section, name="delete_section"),

    path("subjects/", views.manage_subjects, name="manage_subjects"),
    path("subjects/<int:pk>/", views.subject_detail, name="subject_detail"),
    path("subjects/<int:pk>/edit/", views.edit_subject, name="edit_subject"),
    path("subjects/<int:pk>/delete/", views.delete_subject, name="delete_subject"),

    path("teachers/", views.manage_teachers, name="manage_teachers"),
    path("teachers/<int:pk>/", views.teacher_detail, name="teacher_detail"),
    path("teachers/<int:pk>/edit/", views.edit_teacher, name="edit_teacher"),
    path("teachers/<int:pk>/delete/", views.delete_teacher, name="delete_teacher"),

    path("section-subjects/<int:pk>/edit/", views.edit_section_subject, name="edit_section_subject"),
    path("section-subjects/<int:pk>/delete/", views.delete_section_subject, name="delete_section_subject"),
]