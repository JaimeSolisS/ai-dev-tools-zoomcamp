from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    # Explicit login/logout only -- deliberately NOT including
    # django.contrib.auth.urls, which also bundles password_change/ and
    # password_reset/. This app has no mail backend and no self-serve
    # password reset (see README): only these two views are wired.
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
