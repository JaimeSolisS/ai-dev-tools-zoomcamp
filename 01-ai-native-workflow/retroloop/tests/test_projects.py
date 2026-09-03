"""Covers issue #5: Project/Membership models, project creation, the
project list/detail views, the join-link flow, and owner-only token
rotation. See AGENTS.md's testing conventions and the issue's acceptance
criteria for what each test maps to.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.urls import reverse

from projects.models import Membership, Project

VALID_PASSWORD = "correct-horse-battery-42"


def make_user(username):
    return User.objects.create_user(username=username, password=VALID_PASSWORD)


@pytest.mark.django_db
def test_creating_a_project_makes_creator_owner_and_facilitator_member(client):
    owner = make_user("owner")
    client.force_login(owner)

    response = client.post(reverse("project-create"), {"name": "Team Alpha"})

    project = Project.objects.get(name="Team Alpha")
    assert response.status_code == 302
    assert response.url == reverse("project-detail", kwargs={"pk": project.pk})
    assert project.owner == owner

    membership = Membership.objects.get(project=project, user=owner)
    assert membership.role == Membership.Role.FACILITATOR
    assert Membership.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_duplicate_membership_for_same_project_and_user_raises_integrity_error():
    owner = make_user("owner")
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)

    with pytest.raises(IntegrityError):
        Membership.objects.create(project=project, user=owner, role=Membership.Role.MEMBER)


@pytest.mark.django_db
def test_visiting_own_join_link_twice_creates_exactly_one_membership(client):
    owner = make_user("owner")
    client.force_login(owner)
    client.post(reverse("project-create"), {"name": "Team Alpha"})
    project = Project.objects.get(name="Team Alpha")

    join_url = reverse("project-join", kwargs={"token": project.join_token})
    first = client.get(join_url)
    second = client.get(join_url)

    assert first.status_code == 302
    assert second.status_code == 302
    assert Membership.objects.filter(project=project, user=owner).count() == 1


@pytest.mark.django_db
def test_new_visitor_joining_via_link_creates_member_row(client):
    owner = make_user("owner")
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)

    joiner = make_user("joiner")
    client.force_login(joiner)

    response = client.get(reverse("project-join", kwargs={"token": project.join_token}))

    assert response.status_code == 302
    assert response.url == reverse("project-detail", kwargs={"pk": project.pk})
    membership = Membership.objects.get(project=project, user=joiner)
    assert membership.role == Membership.Role.MEMBER


@pytest.mark.django_db
def test_join_with_unknown_token_404s(client):
    user = make_user("visitor")
    client.force_login(user)

    fake_token = "00000000-0000-0000-0000-000000000000"
    response = client.get(reverse("project-join", kwargs={"token": fake_token}))

    assert response.status_code == 404


@pytest.mark.django_db
def test_unauthenticated_join_request_redirects_to_login_then_completes_after_login(client):
    owner = make_user("owner")
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)
    joiner = make_user("joiner")

    join_url = reverse("project-join", kwargs={"token": project.join_token})
    response = client.get(join_url)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert response.url == f"{reverse('login')}?next={join_url}"

    # Completing login with `next` set lands back on the join URL, and the
    # membership is created at that point (standard Django redirect
    # chain -- no custom session stashing).
    login_response = client.post(
        f"{reverse('login')}?next={join_url}",
        {"username": joiner.username, "password": VALID_PASSWORD},
    )
    assert login_response.status_code == 302
    assert login_response.url == join_url

    follow_up = client.get(join_url)
    assert follow_up.status_code == 302
    assert follow_up.url == reverse("project-detail", kwargs={"pk": project.pk})
    assert Membership.objects.filter(project=project, user=joiner).exists()


@pytest.mark.django_db
def test_rotating_token_changes_it_and_old_token_join_url_404s(client):
    owner = make_user("owner")
    client.force_login(owner)
    client.post(reverse("project-create"), {"name": "Team Alpha"})
    project = Project.objects.get(name="Team Alpha")
    old_token = project.join_token

    response = client.post(reverse("project-rotate-token", kwargs={"pk": project.pk}))
    assert response.status_code == 302

    project.refresh_from_db()
    assert project.join_token != old_token

    old_join_response = client.get(reverse("project-join", kwargs={"token": old_token}))
    assert old_join_response.status_code == 404

    new_join_response = client.get(reverse("project-join", kwargs={"token": project.join_token}))
    assert new_join_response.status_code == 302


@pytest.mark.django_db
def test_non_owner_facilitator_cannot_rotate_token(client):
    owner = make_user("owner")
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)

    other_facilitator = make_user("other-facilitator")
    Membership.objects.create(
        project=project, user=other_facilitator, role=Membership.Role.FACILITATOR
    )
    client.force_login(other_facilitator)

    old_token = project.join_token
    response = client.post(reverse("project-rotate-token", kwargs={"pk": project.pk}))

    assert response.status_code == 403
    project.refresh_from_db()
    assert project.join_token == old_token


@pytest.mark.django_db
def test_non_member_requesting_project_detail_gets_404(client):
    owner = make_user("owner")
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)

    outsider = make_user("outsider")
    client.force_login(outsider)

    response = client.get(reverse("project-detail", kwargs={"pk": project.pk}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_project_list_for_user_with_zero_memberships_is_empty_not_an_error(client):
    user = make_user("lonely")
    client.force_login(user)

    response = client.get(reverse("project-list"))

    assert response.status_code == 200
    assert list(response.context["projects"]) == []


@pytest.mark.django_db
def test_project_list_only_shows_projects_user_is_a_member_of(client):
    owner = make_user("owner")
    mine = Project.objects.create(name="Mine", owner=owner)
    Membership.objects.create(project=mine, user=owner, role=Membership.Role.FACILITATOR)

    other_owner = make_user("other-owner")
    other = Project.objects.create(name="Not mine", owner=other_owner)
    Membership.objects.create(project=other, user=other_owner, role=Membership.Role.FACILITATOR)

    client.force_login(owner)
    response = client.get(reverse("project-list"))

    projects = list(response.context["projects"])
    assert projects == [mine]


@pytest.mark.django_db
def test_project_create_requires_login(client):
    response = client.post(reverse("project-create"), {"name": "Team Alpha"})
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert not Project.objects.filter(name="Team Alpha").exists()
