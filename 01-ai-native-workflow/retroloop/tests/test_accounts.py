"""Covers issue #4: signup, login, logout, and the absence of any
password-reset URL. See AGENTS.md's testing conventions and the issue's
acceptance criteria for what each test maps to.
"""

import pytest
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse
from django.urls import NoReverseMatch, reverse

VALID_PASSWORD = "correct-horse-battery-42"


@pytest.mark.django_db
def test_signup_page_has_no_email_field(client):
    response = client.get(reverse("signup"))
    assert response.status_code == 200
    form = response.context["form"]
    assert list(form.fields.keys()) == ["username", "first_name", "password1", "password2"]
    assert b"email" not in response.content.lower()


@pytest.mark.django_db
def test_signup_success_creates_user_logs_in_and_redirects_home(client):
    response = client.post(
        reverse("signup"),
        {
            "username": "grace",
            "first_name": "Grace Hopper",
            "password1": VALID_PASSWORD,
            "password2": VALID_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("home")

    user = User.objects.get(username="grace")
    assert user.first_name == "Grace Hopper"

    # Logged in: home responds 200 and the session carries an authenticated
    # user.
    assert "_auth_user_id" in client.session
    assert int(client.session["_auth_user_id"]) == user.pk


@pytest.mark.django_db
def test_signup_requires_display_name(client):
    response = client.post(
        reverse("signup"),
        {
            "username": "noname",
            "first_name": "",
            "password1": VALID_PASSWORD,
            "password2": VALID_PASSWORD,
        },
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert not form.is_valid()
    assert "first_name" in form.errors
    assert not User.objects.filter(username="noname").exists()


@pytest.mark.django_db
def test_signup_rejects_duplicate_username_without_losing_display_name(client):
    User.objects.create_user(username="taken", password=VALID_PASSWORD)

    response = client.post(
        reverse("signup"),
        {
            "username": "taken",
            "first_name": "Ada Lovelace",
            "password1": VALID_PASSWORD,
            "password2": VALID_PASSWORD,
        },
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert not form.is_valid()
    assert "username" in form.errors
    # The display name the visitor typed is preserved in the re-rendered
    # form, not lost.
    assert response.context["form"]["first_name"].value() == "Ada Lovelace"
    assert b"Ada Lovelace" in response.content
    # Still only the one pre-existing user -- signup did not create a
    # second row.
    assert User.objects.filter(username="taken").count() == 1


@pytest.mark.django_db
def test_signup_rejects_password_failing_validators(client):
    response = client.post(
        reverse("signup"),
        {
            "username": "shortpw",
            "first_name": "Short Pw",
            "password1": "short12",
            "password2": "short12",
        },
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert not form.is_valid()
    assert "password2" in form.errors
    assert not User.objects.filter(username="shortpw").exists()


@pytest.mark.django_db
def test_login_success_redirects_home(client):
    User.objects.create_user(username="grace", password=VALID_PASSWORD)

    response = client.post(
        reverse("login"),
        {"username": "grace", "password": VALID_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_login_failure_shows_non_field_error_without_naming_the_field(client):
    User.objects.create_user(username="grace", password=VALID_PASSWORD)

    response = client.post(
        reverse("login"),
        {"username": "grace", "password": "wrong-password"},
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert not form.is_valid()
    assert form.non_field_errors()
    assert "username" not in form.errors
    assert "password" not in form.errors
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_logout_is_post_only_and_clears_session(client):
    user = User.objects.create_user(username="grace", password=VALID_PASSWORD)
    client.force_login(user)
    assert "_auth_user_id" in client.session

    # GET is not allowed on LogoutView in this Django version.
    get_response = client.get(reverse("logout"))
    assert get_response.status_code == 405

    post_response = client.post(reverse("logout"))
    assert post_response.status_code == 302
    assert post_response.url == reverse("home")
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_logged_in_user_redirected_away_from_signup(client):
    user = User.objects.create_user(username="grace", password=VALID_PASSWORD)
    client.force_login(user)

    response = client.get(reverse("signup"))
    assert response.status_code == 302
    assert response.url == reverse("home")


@pytest.mark.django_db
def test_logged_in_user_redirected_away_from_login(client):
    user = User.objects.create_user(username="grace", password=VALID_PASSWORD)
    client.force_login(user)

    response = client.get(reverse("login"))
    assert response.status_code == 302
    assert response.url == reverse("home")


def test_login_url_setting_points_to_login_route(settings):
    assert settings.LOGIN_URL == "login"
    assert reverse(settings.LOGIN_URL) == "/accounts/login/"


def test_login_required_redirects_anonymous_visitor_to_login(rf):
    """Smoke test for settings.LOGIN_URL, per the issue: no protected view
    exists in this app yet (the first lands in #5), so a throwaway view is
    decorated here just to exercise the redirect."""

    @login_required
    def throwaway(request):
        return HttpResponse("ok")

    request = rf.get("/throwaway/")
    request.user = AnonymousUser()

    response = throwaway(request)

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    ["password_change", "password_change_done", "password_reset", "password_reset_done"],
)
def test_password_reset_urls_are_not_routed(client, url_name):
    # These names aren't wired at all, so reverse() itself must fail --
    # proof the URLs were never included, not just hidden behind a 404 view.
    with pytest.raises(NoReverseMatch):
        reverse(url_name)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/accounts/password_change/",
        "/accounts/password_change/done/",
        "/accounts/password_reset/",
        "/accounts/password_reset/done/",
        "/accounts/reset/done/",
    ],
)
def test_password_reset_paths_404(client, path):
    response = client.get(path)
    assert response.status_code == 404
