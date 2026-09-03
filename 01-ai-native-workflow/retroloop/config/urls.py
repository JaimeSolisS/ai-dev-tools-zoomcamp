from django.contrib import admin
from django.shortcuts import render
from django.urls import path


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
]
