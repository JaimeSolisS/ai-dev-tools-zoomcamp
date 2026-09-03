from django.urls import path

from retro import views

urlpatterns = [
    path("retros/<int:pk>/advance/", views.retrospective_advance, name="retrospective-advance"),
]
