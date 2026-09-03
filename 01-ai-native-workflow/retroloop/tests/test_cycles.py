"""Covers issue #7: `FeedbackCycle` model, its create/close views, and the
`can_create_cycle`/`can_close_cycle` predicates. See the issue's
acceptance criteria for what each test maps to.
"""

from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import IntegrityError, transaction
from django.template.defaultfilters import date as date_filter
from django.urls import reverse

from cycles.models import FeedbackCycle
from projects.models import Membership, Project
from projects.permissions import can_close_cycle, can_create_cycle

VALID_PASSWORD = "correct-horse-battery-42"
WEEK_START = date(2026, 9, 7)


def make_user(username):
    return User.objects.create_user(username=username, password=VALID_PASSWORD)


@pytest.fixture
def owner(db):
    return make_user("owner")


@pytest.fixture
def project(owner):
    project = Project.objects.create(name="Team Alpha", owner=owner)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.FACILITATOR)
    return project


# -- creation -------------------------------------------------------------


@pytest.mark.django_db
def test_member_can_create_cycle_defaulting_facilitator_to_self(client, owner, project):
    client.force_login(owner)

    response = client.post(
        reverse("cycle-create", kwargs={"project_pk": project.pk}),
        {"week_start": WEEK_START, "facilitator": owner.pk},
    )

    assert response.status_code == 302
    assert response.url == reverse("project-detail", kwargs={"pk": project.pk})
    cycle = FeedbackCycle.objects.get(project=project)
    assert cycle.week_start == WEEK_START
    assert cycle.facilitator == owner
    assert cycle.status == FeedbackCycle.Status.COLLECTING
    assert cycle.opens_at is not None
    assert cycle.closes_at is None


@pytest.mark.django_db
def test_plain_member_can_create_cycle_and_assign_another_member_as_facilitator(
    client, owner, project
):
    member = make_user("member")
    Membership.objects.create(project=project, user=member, role=Membership.Role.MEMBER)
    client.force_login(member)

    response = client.post(
        reverse("cycle-create", kwargs={"project_pk": project.pk}),
        {"week_start": WEEK_START, "facilitator": owner.pk},
    )

    assert response.status_code == 302
    cycle = FeedbackCycle.objects.get(project=project)
    assert cycle.facilitator == owner


@pytest.mark.django_db
def test_non_member_cannot_create_cycle(client, project):
    outsider = make_user("outsider")
    client.force_login(outsider)

    response = client.post(
        reverse("cycle-create", kwargs={"project_pk": project.pk}),
        {"week_start": WEEK_START, "facilitator": outsider.pk},
    )

    assert response.status_code == 403
    assert not FeedbackCycle.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_assigning_non_member_as_facilitator_is_rejected_by_form(client, owner, project):
    outsider = make_user("outsider")
    client.force_login(owner)

    response = client.post(
        reverse("cycle-create", kwargs={"project_pk": project.pk}),
        {"week_start": WEEK_START, "facilitator": outsider.pk},
    )

    assert response.status_code == 200
    assert "facilitator" in response.context["form"].errors
    assert not FeedbackCycle.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_create_rejected_with_clean_error_while_a_cycle_is_collecting(client, owner, project):
    client.force_login(owner)
    client.post(
        reverse("cycle-create", kwargs={"project_pk": project.pk}),
        {"week_start": WEEK_START, "facilitator": owner.pk},
    )
    assert FeedbackCycle.objects.filter(project=project).count() == 1

    response = client.post(
        reverse("cycle-create", kwargs={"project_pk": project.pk}),
        {"week_start": date(2026, 9, 14), "facilitator": owner.pk},
    )

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert FeedbackCycle.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_db_constraint_directly_rejects_second_collecting_cycle_for_same_project(owner, project):
    """Model-level test hitting the DB constraint directly (not the view),
    per issue #7: proves `one_collecting_cycle_per_project` is enforced at
    the database layer even if application logic were bypassed entirely."""
    FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FeedbackCycle.objects.create(
                project=project, week_start=date(2026, 9, 14), facilitator=owner
            )


@pytest.mark.django_db
def test_db_constraint_allows_a_new_collecting_cycle_once_the_first_is_closed(owner, project):
    first = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    first.close()

    second = FeedbackCycle.objects.create(
        project=project, week_start=date(2026, 9, 14), facilitator=owner
    )
    assert second.status == FeedbackCycle.Status.COLLECTING


# -- closing ----------------------------------------------------------------


@pytest.mark.django_db
def test_facilitator_can_close_cycle(client, owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    client.force_login(owner)

    response = client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))

    assert response.status_code == 302
    cycle.refresh_from_db()
    assert cycle.status == FeedbackCycle.Status.CLOSED
    assert cycle.closes_at is not None


@pytest.mark.django_db
def test_project_owner_who_is_not_facilitator_cannot_close_cycle(client, owner, project):
    facilitator = make_user("facilitator")
    Membership.objects.create(project=project, user=facilitator, role=Membership.Role.MEMBER)
    cycle = FeedbackCycle.objects.create(
        project=project, week_start=WEEK_START, facilitator=facilitator
    )
    client.force_login(owner)

    response = client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))

    assert response.status_code == 403
    cycle.refresh_from_db()
    assert cycle.status == FeedbackCycle.Status.COLLECTING


@pytest.mark.django_db
def test_other_member_cannot_close_cycle(client, owner, project):
    other_member = make_user("other-member")
    Membership.objects.create(project=project, user=other_member, role=Membership.Role.MEMBER)
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    client.force_login(other_member)

    response = client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))

    assert response.status_code == 403
    cycle.refresh_from_db()
    assert cycle.status == FeedbackCycle.Status.COLLECTING


@pytest.mark.django_db
def test_non_member_cannot_close_cycle(client, owner, project):
    outsider = make_user("outsider")
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    client.force_login(outsider)

    response = client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))

    assert response.status_code == 403
    cycle.refresh_from_db()
    assert cycle.status == FeedbackCycle.Status.COLLECTING


@pytest.mark.django_db
def test_anonymous_user_cannot_close_cycle(client, owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)

    response = client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    cycle.refresh_from_db()
    assert cycle.status == FeedbackCycle.Status.COLLECTING


@pytest.mark.django_db
def test_double_close_is_idempotent_and_does_not_restamp_closes_at(client, owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    client.force_login(owner)

    client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))
    cycle.refresh_from_db()
    first_closes_at = cycle.closes_at

    response = client.post(reverse("cycle-close", kwargs={"pk": cycle.pk}))

    assert response.status_code == 302
    cycle.refresh_from_db()
    assert cycle.status == FeedbackCycle.Status.CLOSED
    assert cycle.closes_at == first_closes_at


@pytest.mark.django_db
def test_model_close_method_is_idempotent(owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    cycle.close()
    first_closes_at = cycle.closes_at

    cycle.close()

    assert cycle.status == FeedbackCycle.Status.CLOSED
    assert cycle.closes_at == first_closes_at


# -- permissions --------------------------------------------------------


@pytest.mark.django_db
def test_can_create_cycle_true_for_any_member_role(project):
    member = make_user("member")
    Membership.objects.create(project=project, user=member, role=Membership.Role.MEMBER)
    assert can_create_cycle(member, project) is True


@pytest.mark.django_db
def test_can_create_cycle_false_for_non_member(project):
    outsider = make_user("outsider")
    assert can_create_cycle(outsider, project) is False


@pytest.mark.django_db
def test_can_create_cycle_false_for_anonymous_user(project):
    assert can_create_cycle(AnonymousUser(), project) is False


@pytest.mark.django_db
def test_can_close_cycle_true_for_facilitator(owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    assert can_close_cycle(owner, cycle) is True


@pytest.mark.django_db
def test_can_close_cycle_false_for_project_owner_who_is_not_facilitator(owner, project):
    facilitator = make_user("facilitator")
    Membership.objects.create(project=project, user=facilitator, role=Membership.Role.MEMBER)
    cycle = FeedbackCycle.objects.create(
        project=project, week_start=WEEK_START, facilitator=facilitator
    )
    assert can_close_cycle(owner, cycle) is False


@pytest.mark.django_db
def test_can_close_cycle_false_for_anonymous_user(owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    assert can_close_cycle(AnonymousUser(), cycle) is False


# -- project detail stub --------------------------------------------------


@pytest.mark.django_db
def test_project_detail_shows_no_open_cycle_when_none_exists(client, owner, project):
    client.force_login(owner)
    response = client.get(reverse("project-detail", kwargs={"pk": project.pk}))
    assert response.context["collecting_cycle"] is None
    assert b"No open cycle" in response.content


@pytest.mark.django_db
def test_project_detail_shows_collecting_cycle_week_start_and_facilitator(client, owner, project):
    cycle = FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)
    client.force_login(owner)

    response = client.get(reverse("project-detail", kwargs={"pk": project.pk}))

    assert response.context["collecting_cycle"] == cycle
    content = response.content.decode()
    assert date_filter(WEEK_START) in content
    assert owner.username in content
