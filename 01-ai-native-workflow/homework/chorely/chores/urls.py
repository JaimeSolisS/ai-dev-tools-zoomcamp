from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.calendar_redirect, name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="chores/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("calendar/<int:year>/<int:month>/", views.calendar_month, name="calendar_month"),
    path("calendar/week/<int:year>/<int:week>/", views.calendar_week, name="calendar_week"),
    path("day/<int:year>/<int:month>/<int:day>/", views.day_detail, name="day_detail"),
    path("chores/new/", views.chore_create, name="chore_create"),
    path("chores/<int:pk>/", views.chore_detail, name="chore_detail"),
    path("chores/<int:pk>/edit/", views.chore_edit, name="chore_edit"),
    path("chores/<int:pk>/claim/", views.chore_claim, name="chore_claim"),
    path("chores/<int:pk>/status/", views.chore_status, name="chore_status"),
    path("history/", views.CompletionHistoryView.as_view(), name="history"),
    path("manage/members/", views.MemberListView.as_view(), name="member_list"),
    path("manage/members/new/", views.MemberCreateView.as_view(), name="member_create"),
    path(
        "manage/members/<int:pk>/remove/",
        views.MemberRemoveView.as_view(),
        name="member_remove",
    ),
]
