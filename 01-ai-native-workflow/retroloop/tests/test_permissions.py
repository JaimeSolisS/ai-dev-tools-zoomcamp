"""Covers issue #6: `projects/permissions.py` predicates over `Project`
and `Membership`. This module is the app's security boundary per
AGENTS.md, so every predicate is tested for both its True and False
cases plus the edge cases the issue calls out explicitly: owner,
non-owner facilitator, plain member, non-member, AnonymousUser, and a
former member whose Membership row was deleted.
"""

import pytest
from django.contrib.auth.models import AnonymousUser, User

from projects.models import Membership, Project
from projects.permissions import (
    can_rotate_join_token,
    can_view_membership_list,
    can_view_project,
)


def make_user(username):
    return User.objects.create_user(username=username, password="irrelevant")


@pytest.fixture
def owner(db):
    return make_user("owner")


@pytest.fixture
def project(owner):
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)
    return project


# -- can_view_project ---------------------------------------------------


@pytest.mark.django_db
def test_can_view_project_true_for_owner(owner, project):
    assert can_view_project(owner, project) is True


@pytest.mark.django_db
def test_can_view_project_true_for_non_owner_facilitator(project):
    facilitator = make_user("facilitator")
    Membership.objects.create(project=project, user=facilitator, role=Membership.Role.FACILITATOR)
    assert can_view_project(facilitator, project) is True


@pytest.mark.django_db
def test_can_view_project_true_for_plain_member(project):
    member = make_user("member")
    Membership.objects.create(project=project, user=member, role=Membership.Role.MEMBER)
    assert can_view_project(member, project) is True


@pytest.mark.django_db
def test_can_view_project_false_for_non_member(project):
    outsider = make_user("outsider")
    assert can_view_project(outsider, project) is False


@pytest.mark.django_db
def test_can_view_project_false_for_anonymous_user(project):
    assert can_view_project(AnonymousUser(), project) is False


@pytest.mark.django_db
def test_can_view_project_false_for_former_member_with_deleted_membership(project):
    former = make_user("former")
    membership = Membership.objects.create(
        project=project, user=former, role=Membership.Role.MEMBER
    )
    membership.delete()
    assert can_view_project(former, project) is False


# -- can_rotate_join_token ------------------------------------------------


@pytest.mark.django_db
def test_can_rotate_join_token_true_for_owner(owner, project):
    assert can_rotate_join_token(owner, project) is True


@pytest.mark.django_db
def test_can_rotate_join_token_false_for_non_owner_facilitator(project):
    facilitator = make_user("facilitator")
    Membership.objects.create(project=project, user=facilitator, role=Membership.Role.FACILITATOR)
    assert can_rotate_join_token(facilitator, project) is False


@pytest.mark.django_db
def test_can_rotate_join_token_false_for_plain_member(project):
    member = make_user("member")
    Membership.objects.create(project=project, user=member, role=Membership.Role.MEMBER)
    assert can_rotate_join_token(member, project) is False


@pytest.mark.django_db
def test_can_rotate_join_token_false_for_non_member(project):
    outsider = make_user("outsider")
    assert can_rotate_join_token(outsider, project) is False


@pytest.mark.django_db
def test_can_rotate_join_token_false_for_anonymous_user(project):
    assert can_rotate_join_token(AnonymousUser(), project) is False


@pytest.mark.django_db
def test_can_rotate_join_token_false_for_former_member_with_deleted_membership(project):
    former = make_user("former")
    membership = Membership.objects.create(
        project=project, user=former, role=Membership.Role.MEMBER
    )
    membership.delete()
    assert can_rotate_join_token(former, project) is False


# -- can_view_membership_list --------------------------------------------


@pytest.mark.django_db
def test_can_view_membership_list_true_for_owner(owner, project):
    assert can_view_membership_list(owner, project) is True


@pytest.mark.django_db
def test_can_view_membership_list_true_for_non_owner_facilitator(project):
    facilitator = make_user("facilitator")
    Membership.objects.create(project=project, user=facilitator, role=Membership.Role.FACILITATOR)
    assert can_view_membership_list(facilitator, project) is True


@pytest.mark.django_db
def test_can_view_membership_list_true_for_plain_member(project):
    member = make_user("member")
    Membership.objects.create(project=project, user=member, role=Membership.Role.MEMBER)
    assert can_view_membership_list(member, project) is True


@pytest.mark.django_db
def test_can_view_membership_list_false_for_non_member(project):
    outsider = make_user("outsider")
    assert can_view_membership_list(outsider, project) is False


@pytest.mark.django_db
def test_can_view_membership_list_false_for_anonymous_user(project):
    assert can_view_membership_list(AnonymousUser(), project) is False


@pytest.mark.django_db
def test_can_view_membership_list_false_for_former_member_with_deleted_membership(project):
    former = make_user("former")
    membership = Membership.objects.create(
        project=project, user=former, role=Membership.Role.MEMBER
    )
    membership.delete()
    assert can_view_membership_list(former, project) is False
