"""Covers issue #8: the `Card` model, its create/edit/delete HTMX views,
the card board, and the `can_add_card`/`can_edit_card`/`can_delete_card`
predicates. See the issue's acceptance criteria for what each test maps
to.
"""

from datetime import date
from urllib.parse import urlencode

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.urls import reverse

from cycles.models import Card, FeedbackCycle
from projects.models import Membership, Project
from projects.permissions import can_add_card, can_delete_card, can_edit_card

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


@pytest.fixture
def cycle(owner, project):
    return FeedbackCycle.objects.create(project=project, week_start=WEEK_START, facilitator=owner)


@pytest.fixture
def member(project):
    user = make_user("member")
    Membership.objects.create(project=project, user=user, role=Membership.Role.MEMBER)
    return user


# -- create -----------------------------------------------------------------


@pytest.mark.django_db
def test_member_can_create_card_and_it_appears_in_own_fragment(client, owner, cycle):
    client.force_login(owner)

    response = client.post(
        reverse("card-create", kwargs={"cycle_pk": cycle.pk}),
        {"category": "START", "text": "Ship faster"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    card = Card.objects.get(cycle=cycle, category="START")
    assert card.text == "Ship faster"
    assert card.author == owner
    assert card.is_anonymous is False
    assert card.position == 0
    content = response.content.decode()
    assert "Ship faster" in content
    assert "<html" not in content


@pytest.mark.django_db
def test_position_auto_increments_per_category(client, owner, cycle):
    client.force_login(owner)
    url = reverse("card-create", kwargs={"cycle_pk": cycle.pk})

    client.post(url, {"category": "START", "text": "First"})
    client.post(url, {"category": "START", "text": "Second"})
    client.post(url, {"category": "STOP", "text": "Third"})

    start_cards = Card.objects.filter(cycle=cycle, category="START").order_by("position")
    assert list(start_cards.values_list("text", "position")) == [
        ("First", 0),
        ("Second", 1),
    ]
    stop_card = Card.objects.get(cycle=cycle, category="STOP")
    assert stop_card.position == 0


@pytest.mark.django_db
def test_create_rejected_on_closed_cycle(client, owner, cycle):
    cycle.close()
    client.force_login(owner)

    response = client.post(
        reverse("card-create", kwargs={"cycle_pk": cycle.pk}),
        {"category": "START", "text": "Too late"},
    )

    assert response.status_code == 200
    assert not Card.objects.filter(cycle=cycle).exists()
    assert b"closed" in response.content.lower()


@pytest.mark.django_db
def test_create_rejected_for_non_member(client, cycle):
    outsider = make_user("outsider")
    client.force_login(outsider)

    response = client.post(
        reverse("card-create", kwargs={"cycle_pk": cycle.pk}),
        {"category": "START", "text": "Sneaky"},
    )

    assert response.status_code == 403
    assert not Card.objects.filter(cycle=cycle).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_create_rejected_for_empty_or_whitespace_text(client, owner, cycle, text):
    client.force_login(owner)

    response = client.post(
        reverse("card-create", kwargs={"cycle_pk": cycle.pk}),
        {"category": "START", "text": text},
    )

    assert response.status_code == 200
    assert not Card.objects.filter(cycle=cycle).exists()


@pytest.mark.django_db
def test_create_anonymous_flag_is_stored(client, owner, cycle):
    client.force_login(owner)

    client.post(
        reverse("card-create", kwargs={"cycle_pk": cycle.pk}),
        {"category": "STOP", "text": "Quiet card", "is_anonymous": "on"},
    )

    card = Card.objects.get(cycle=cycle, category="STOP")
    assert card.is_anonymous is True
    assert card.author == owner  # not nulled by this task -- that's #10


# -- board / queryset ---------------------------------------------------


@pytest.mark.django_db
def test_board_only_returns_requesting_members_own_cards(client, owner, member, cycle):
    Card.objects.create(cycle=cycle, category="START", text="Owner card", author=owner, position=0)
    Card.objects.create(
        cycle=cycle, category="START", text="Member card", author=member, position=1
    )
    client.force_login(owner)

    response = client.get(reverse("card-board", kwargs={"cycle_pk": cycle.pk}))

    content = response.content.decode()
    assert "Owner card" in content
    assert "Member card" not in content


@pytest.mark.django_db
def test_board_context_columns_never_contain_other_members_cards(client, owner, member, cycle):
    Card.objects.create(cycle=cycle, category="STOP", text="Owner card", author=owner, position=0)
    Card.objects.create(
        cycle=cycle, category="STOP", text="Member card", author=member, position=1
    )
    client.force_login(owner)

    response = client.get(reverse("card-board", kwargs={"cycle_pk": cycle.pk}))

    for _value, _label, cards in response.context["columns"]:
        for card in cards:
            assert card.author_id == owner.id


@pytest.mark.django_db
def test_board_rejected_for_non_member(client, cycle):
    outsider = make_user("outsider")
    client.force_login(outsider)

    response = client.get(reverse("card-board", kwargs={"cycle_pk": cycle.pk}))

    assert response.status_code == 403


# -- edit -----------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_edit_own_card(client, owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Old text", author=owner)
    client.force_login(owner)

    response = client.put(
        reverse("card-edit", kwargs={"pk": card.pk}),
        urlencode({"text": "New text"}),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.text == "New text"
    assert "New text" in response.content.decode()


@pytest.mark.django_db
def test_editing_another_members_card_returns_404(client, owner, member, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Member's card", author=member)
    client.force_login(owner)

    response = client.put(
        reverse("card-edit", kwargs={"pk": card.pk}),
        urlencode({"text": "Hijacked"}),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 404
    card.refresh_from_db()
    assert card.text == "Member's card"


@pytest.mark.django_db
def test_editing_own_card_on_closed_cycle_is_rejected(client, owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Old text", author=owner)
    cycle.close()
    client.force_login(owner)

    response = client.put(
        reverse("card-edit", kwargs={"pk": card.pk}),
        urlencode({"text": "New text"}),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.text == "Old text"
    assert b"closed" in response.content.lower()


@pytest.mark.django_db
def test_non_member_editing_card_by_guessed_id_returns_404(client, cycle, owner):
    card = Card.objects.create(cycle=cycle, category="START", text="Text", author=owner)
    outsider = make_user("outsider")
    client.force_login(outsider)

    response = client.put(
        reverse("card-edit", kwargs={"pk": card.pk}),
        urlencode({"text": "Hijacked"}),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 404


# -- delete -----------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_delete_own_card(client, owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Doomed", author=owner)
    client.force_login(owner)

    response = client.delete(reverse("card-delete", kwargs={"pk": card.pk}))

    assert response.status_code == 200
    assert response.content == b""
    assert not Card.objects.filter(pk=card.pk).exists()


@pytest.mark.django_db
def test_deleting_already_deleted_card_returns_404_not_500(client, owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Doomed", author=owner)
    client.force_login(owner)
    first = client.delete(reverse("card-delete", kwargs={"pk": card.pk}))
    assert first.status_code == 200

    second = client.delete(reverse("card-delete", kwargs={"pk": card.pk}))

    assert second.status_code == 404


@pytest.mark.django_db
def test_deleting_another_members_card_returns_404(client, owner, member, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Member's card", author=member)
    client.force_login(owner)

    response = client.delete(reverse("card-delete", kwargs={"pk": card.pk}))

    assert response.status_code == 404
    assert Card.objects.filter(pk=card.pk).exists()


@pytest.mark.django_db
def test_deleting_own_card_on_closed_cycle_is_rejected(client, owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Kept", author=owner)
    cycle.close()
    client.force_login(owner)

    response = client.delete(reverse("card-delete", kwargs={"pk": card.pk}))

    assert response.status_code == 403
    assert Card.objects.filter(pk=card.pk).exists()


@pytest.mark.django_db
def test_non_member_deleting_card_by_guessed_id_returns_404(client, cycle, owner):
    card = Card.objects.create(cycle=cycle, category="START", text="Text", author=owner)
    outsider = make_user("outsider")
    client.force_login(outsider)

    response = client.delete(reverse("card-delete", kwargs={"pk": card.pk}))

    assert response.status_code == 404
    assert Card.objects.filter(pk=card.pk).exists()


# -- permissions --------------------------------------------------------


@pytest.mark.django_db
def test_can_add_card_true_for_member_on_collecting_cycle(member, cycle):
    assert can_add_card(member, cycle) is True


@pytest.mark.django_db
def test_can_add_card_false_for_non_member(cycle):
    outsider = make_user("outsider")
    assert can_add_card(outsider, cycle) is False


@pytest.mark.django_db
def test_can_add_card_false_when_cycle_closed(member, cycle):
    cycle.close()
    assert can_add_card(member, cycle) is False


@pytest.mark.django_db
def test_can_add_card_false_for_anonymous_user(cycle):
    assert can_add_card(AnonymousUser(), cycle) is False


@pytest.mark.django_db
def test_can_edit_card_true_for_author_on_collecting_cycle(owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    assert can_edit_card(owner, card) is True


@pytest.mark.django_db
def test_can_edit_card_false_for_non_author(owner, member, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    assert can_edit_card(member, card) is False


@pytest.mark.django_db
def test_can_edit_card_false_when_cycle_closed(owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    cycle.close()
    assert can_edit_card(owner, card) is False


@pytest.mark.django_db
def test_can_edit_card_false_for_anonymous_user(owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    assert can_edit_card(AnonymousUser(), card) is False


@pytest.mark.django_db
def test_can_delete_card_true_for_author_on_collecting_cycle(owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    assert can_delete_card(owner, card) is True


@pytest.mark.django_db
def test_can_delete_card_false_for_non_author(owner, member, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    assert can_delete_card(member, card) is False


@pytest.mark.django_db
def test_can_delete_card_false_when_cycle_closed(owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    cycle.close()
    assert can_delete_card(owner, card) is False


@pytest.mark.django_db
def test_can_delete_card_false_for_anonymous_user(owner, cycle):
    card = Card.objects.create(cycle=cycle, category="START", text="Mine", author=owner)
    assert can_delete_card(AnonymousUser(), card) is False
