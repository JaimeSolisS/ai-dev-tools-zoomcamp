from django.urls import path

from projects import views

urlpatterns = [
    path("", views.project_list, name="project-list"),
    path("new/", views.project_create, name="project-create"),
    path("<int:pk>/", views.project_detail, name="project-detail"),
    path("<int:pk>/rotate-token/", views.rotate_token, name="project-rotate-token"),
]
