from django.urls import path

from cycles import views

urlpatterns = [
    path("projects/<int:project_pk>/cycles/new/", views.cycle_create, name="cycle-create"),
    path("cycles/<int:pk>/close/", views.cycle_close, name="cycle-close"),
]
