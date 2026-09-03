from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from projects import views as project_views


def home(request):
    return render(request, "home.html")


def htmx_demo(request):
    """Placeholder HTMX target: always returns just the fragment, never the
    base.html chrome, so it can't be confused with a full page render (see
    issue #3's edge cases)."""
    return render(request, "partials/htmx_demo_result.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("htmx-demo/", htmx_demo, name="htmx-demo"),
    # Only login/logout/signup are wired here (accounts/urls.py) --
    # deliberately not the full django.contrib.auth.urls include, which
    # also bundles password_change/ and password_reset/. See #4.
    path("accounts/", include("accounts.urls")),
    path("projects/", include("projects.urls")),
    # Top-level per issue #5: the join link is `/join/<token>/`, not
    # namespaced under /projects/.
    path("join/<uuid:token>/", project_views.join, name="project-join"),
]
