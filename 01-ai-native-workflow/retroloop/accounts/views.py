from django.contrib.auth import login
from django.shortcuts import redirect, render

from accounts.forms import SignupForm


def signup(request):
    """GET/POST /accounts/signup/.

    A logged-in visitor is redirected to `home` rather than shown the form
    again (see issue #4). On success the new user is logged in immediately
    and sent to `home`, matching the login flow.
    """
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = SignupForm()

    return render(request, "accounts/signup.html", {"form": form})
