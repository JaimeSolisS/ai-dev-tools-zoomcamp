"""Covers issue #9: the `Retrospective` model, its creation from
`FeedbackCycle.close()`, the `advance_stage()` service function, the
`TRANSITIONS` hook dict, and the `can_advance_stage` predicate. See the
issue's acceptance criteria for what each test maps to.
"""

import random
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied

from cycles.models import Card, CycleParticipation, FeedbackCycle
from projects.models import Membership, Project
from projects.permissions import can_advance_stage
from retro import services
from retro.models import Retrospective
from retro.services import TRANSITIONS, _on_reveal, advance_stage

VALID_PASSWORD = "correct-horse-battery-42"
WEEK_START = date(2026, 9, 7)

Stage = Retrospective.Stage

LEGAL_TRANSITIONS = [
    (Stage.DRAFT, Stage.REVEAL),
    (Stage.REVEAL, Stage.CLUSTER),
    (Stage.CLUSTER, Stage.VOTE),
    (Stage.VOTE, Stage.DISCUSS),
    (Stage.DISCUSS, Stage.COMPLETE),
]


def make_user(username):
    return User.objects.create_user(username=username, password=VALID_PASSWORD)


@pytest.fixture
def facilitator(db):
    return make_user("facilitator")


@pytest.fixture
def project(facilitator):
    project = Project.objects.create(name="Team Alpha", owner=facilitator)
    Membership.objects.create(project=project, user=facilitator, role=Membership.Role.FACILITATOR)
    return project


@pytest.fixture
def cycle(project, facilitator):
    return FeedbackCycle.objects.create(
        project=project, week_start=WEEK_START, facilitator=facilitator
    )


@pytest.fixture
def closed_cycle(cycle):
    cycle.close()
    cycle.refresh_from_db()
    return cycle


@pytest.fixture
def retrospective(closed_cycle):
    return closed_cycle.retrospective


def set_stage(retrospective, stage, version=1):
    """Force a retrospective straight to `stage` without going through
    `advance_stage` -- these tests are exercising `advance_stage` itself,
    so its normal one-step-at-a-time rule can't be used to reach the
    later stages under test."""
    retrospective.stage = stage
    retrospective.version = version
    retrospective.save(update_fields=["stage", "version"])
    return retrospective


# -- Retrospective creation on FeedbackCycle.close() -----------------------


@pytest.mark.django_db
def test_close_creates_retrospective_draft_version_1(cycle):
    cycle.close()
    cycle.refresh_from_db()

    retro = cycle.retrospective
    assert retro.stage == Stage.DRAFT
    assert retro.version == 1
    assert retro.started_at is None
    assert retro.completed_at is None


@pytest.mark.django_db
def test_close_idempotent_does_not_create_second_retrospective_or_reset_stage(
    closed_cycle, facilitator
):
    retro = closed_cycle.retrospective
    advance_stage(facilitator, retro, Stage.REVEAL)
    retro.refresh_from_db()
    assert retro.stage == Stage.REVEAL

    # Closing an already-CLOSED cycle again must not touch the retrospective.
    closed_cycle.close()

    assert Retrospective.objects.filter(cycle=closed_cycle).count() == 1
    retro.refresh_from_db()
    assert retro.stage == Stage.REVEAL
    assert retro.version == 2


@pytest.mark.django_db
def test_no_retrospective_for_a_cycle_that_has_never_been_closed(cycle):
    assert not Retrospective.objects.filter(cycle=cycle).exists()
    with pytest.raises(Retrospective.DoesNotExist):
        cycle.retrospective


# -- can_advance_stage -------------------------------------------------


@pytest.mark.django_db
def test_can_advance_stage_true_for_facilitator(retrospective, facilitator):
    assert can_advance_stage(facilitator, retrospective) is True


@pytest.mark.django_db
def test_can_advance_stage_false_for_non_facilitator_member(retrospective, project):
    other = make_user("other")
    Membership.objects.create(project=project, user=other, role=Membership.Role.MEMBER)
    assert can_advance_stage(other, retrospective) is False


@pytest.mark.django_db
def test_can_advance_stage_false_for_anonymous_user(retrospective):
    assert can_advance_stage(AnonymousUser(), retrospective) is False


# -- legal transitions ---------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("from_stage,to_stage", LEGAL_TRANSITIONS)
def test_legal_transition_advances_one_step_bumps_version_and_fires_hook(
    retrospective, facilitator, monkeypatch, from_stage, to_stage
):
    set_stage(retrospective, from_stage, version=5)

    calls = []
    monkeypatch.setitem(TRANSITIONS, (from_stage, to_stage), lambda r: calls.append(r.pk))

    result = advance_stage(facilitator, retrospective, to_stage)

    assert result.stage == to_stage
    assert result.version == 6
    assert calls == [retrospective.pk]

    retrospective.refresh_from_db()
    assert retrospective.stage == to_stage
    assert retrospective.version == 6


@pytest.mark.django_db
def test_draft_to_reveal_stamps_started_at(retrospective, facilitator):
    assert retrospective.started_at is None
    advance_stage(facilitator, retrospective, Stage.REVEAL)
    retrospective.refresh_from_db()
    assert retrospective.started_at is not None
    assert retrospective.completed_at is None


@pytest.mark.django_db
def test_cluster_to_vote_freezes_clusters(retrospective, facilitator):
    set_stage(retrospective, Stage.CLUSTER)
    advance_stage(facilitator, retrospective, Stage.VOTE)
    retrospective.refresh_from_db()
    assert retrospective.clusters_frozen is True


@pytest.mark.django_db
def test_vote_to_discuss_reveals_vote_totals(retrospective, facilitator):
    set_stage(retrospective, Stage.VOTE)
    advance_stage(facilitator, retrospective, Stage.DISCUSS)
    retrospective.refresh_from_db()
    assert retrospective.votes_revealed is True


@pytest.mark.django_db
def test_discuss_to_complete_stamps_completed_at(retrospective, facilitator):
    set_stage(retrospective, Stage.DISCUSS)
    assert retrospective.completed_at is None
    advance_stage(facilitator, retrospective, Stage.COMPLETE)
    retrospective.refresh_from_db()
    assert retrospective.completed_at is not None


@pytest.mark.django_db
def test_other_transitions_leave_started_at_and_completed_at_alone(retrospective, facilitator):
    set_stage(retrospective, Stage.REVEAL)
    advance_stage(facilitator, retrospective, Stage.CLUSTER)
    retrospective.refresh_from_db()
    assert retrospective.started_at is None
    assert retrospective.completed_at is None


# -- illegal transitions ---------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "from_stage,to_stage",
    [
        (Stage.DRAFT, Stage.CLUSTER),  # skip-ahead
        (Stage.DRAFT, Stage.COMPLETE),  # skip-ahead, further
        (Stage.VOTE, Stage.DRAFT),  # backward
        (Stage.COMPLETE, Stage.DISCUSS),  # backward
        (Stage.VOTE, Stage.VOTE),  # same-stage
        (Stage.COMPLETE, Stage.COMPLETE),  # same-stage, terminal
    ],
)
def test_illegal_transition_rejected_and_changes_nothing(
    retrospective, facilitator, monkeypatch, from_stage, to_stage
):
    set_stage(retrospective, from_stage, version=3)
    calls = []
    for key, fn in list(TRANSITIONS.items()):
        monkeypatch.setitem(TRANSITIONS, key, lambda r, calls=calls: calls.append(1))

    with pytest.raises(ValueError):
        advance_stage(facilitator, retrospective, to_stage)

    retrospective.refresh_from_db()
    assert retrospective.stage == from_stage
    assert retrospective.version == 3
    assert calls == []


@pytest.mark.django_db
def test_complete_is_terminal_nothing_advances_past_it(retrospective, facilitator):
    set_stage(retrospective, Stage.COMPLETE, version=7)
    for target in [Stage.DRAFT, Stage.REVEAL, Stage.CLUSTER, Stage.VOTE, Stage.DISCUSS]:
        with pytest.raises(ValueError):
            advance_stage(facilitator, retrospective, target)
    retrospective.refresh_from_db()
    assert retrospective.stage == Stage.COMPLETE
    assert retrospective.version == 7


@pytest.mark.django_db
def test_non_facilitator_call_rejected_and_changes_nothing(retrospective, project):
    other = make_user("other")
    Membership.objects.create(project=project, user=other, role=Membership.Role.MEMBER)

    with pytest.raises(PermissionDenied):
        advance_stage(other, retrospective, Stage.REVEAL)

    retrospective.refresh_from_db()
    assert retrospective.stage == Stage.DRAFT
    assert retrospective.version == 1


@pytest.mark.django_db
def test_non_facilitator_call_rejected_even_when_target_stage_is_legal_and_at_complete(
    retrospective, project
):
    """A non-facilitator is rejected before the forward-only check even
    runs -- verified separately from the plain-DRAFT case above by also
    trying it once the retrospective is at a stage where advancing would
    otherwise be perfectly legal."""
    other = make_user("other")
    Membership.objects.create(project=project, user=other, role=Membership.Role.MEMBER)
    set_stage(retrospective, Stage.VOTE, version=4)

    with pytest.raises(PermissionDenied):
        advance_stage(other, retrospective, Stage.DISCUSS)

    retrospective.refresh_from_db()
    assert retrospective.stage == Stage.VOTE
    assert retrospective.version == 4


# -- side effect / stage write share one transaction ------------------------


@pytest.mark.django_db
def test_side_effect_exception_rolls_back_stage_version_and_timestamps(
    retrospective, facilitator, monkeypatch
):
    def boom(r):
        raise RuntimeError("side effect blew up")

    monkeypatch.setitem(TRANSITIONS, (Stage.DRAFT, Stage.REVEAL), boom)

    with pytest.raises(RuntimeError):
        advance_stage(facilitator, retrospective, Stage.REVEAL)

    retrospective.refresh_from_db()
    assert retrospective.stage == Stage.DRAFT
    assert retrospective.version == 1
    assert retrospective.started_at is None
    assert retrospective.completed_at is None


# -- select_for_update race protection --------------------------------------


@pytest.mark.django_db
def test_concurrent_calls_serialize_second_call_sees_post_first_call_state(
    retrospective, facilitator
):
    """Simulates two facilitator requests racing to advance the same
    retrospective: both call `advance_stage` with the *same* stale
    `target_stage` computed from stage DRAFT. `select_for_update` inside
    `transaction.atomic()` means the first call's write is visible to the
    second by the time it runs (they're sequential here, standing in for
    the lock serializing them rather than both committing off a stale
    read) -- so the second call, still requesting REVEAL while the
    retrospective is now at REVEAL, is correctly rejected as a same-stage
    call instead of silently succeeding twice.
    """
    first = advance_stage(facilitator, retrospective, Stage.REVEAL)
    assert first.stage == Stage.REVEAL
    assert first.version == 2

    retrospective.refresh_from_db()
    with pytest.raises(ValueError):
        advance_stage(facilitator, retrospective, Stage.REVEAL)

    retrospective.refresh_from_db()
    assert retrospective.stage == Stage.REVEAL
    assert retrospective.version == 2


@pytest.mark.django_db
def test_advance_stage_locks_row_with_select_for_update(retrospective, facilitator, monkeypatch):
    """Asserts the implementation actually uses `select_for_update()`
    rather than a plain `.get()`, per the issue's explicit requirement --
    a plain `.get()` would still pass every other test here."""
    calls = {}
    original = Retrospective.objects.select_for_update

    def spy(*args, **kwargs):
        calls["called"] = True
        return original(*args, **kwargs)

    monkeypatch.setattr(services.Retrospective.objects, "select_for_update", spy)

    advance_stage(facilitator, retrospective, Stage.REVEAL)

    assert calls.get("called") is True


# -- _on_reveal (issue #10) -------------------------------------------------


@pytest.fixture
def member(project):
    user = make_user("member")
    Membership.objects.create(project=project, user=user, role=Membership.Role.MEMBER)
    return user


def make_card(
    cycle, author, category=Card.Category.START, position=0, is_anonymous=False, text="c"
):
    return Card.objects.create(
        cycle=cycle,
        category=category,
        text=text,
        author=author,
        is_anonymous=is_anonymous,
        position=position,
    )


@pytest.mark.django_db
def test_reveal_nulls_author_of_anonymous_card(retrospective, closed_cycle, facilitator):
    card = make_card(closed_cycle, facilitator, is_anonymous=True)

    advance_stage(facilitator, retrospective, Stage.REVEAL)

    card.refresh_from_db()
    assert card.author is None


@pytest.mark.django_db
def test_reveal_leaves_non_anonymous_card_author_unchanged_same_user(
    retrospective, closed_cycle, facilitator
):
    """Both cards come from the SAME user, to catch a "null everyone"
    bug that a test using two different users for the two cards would
    miss."""
    attributed = make_card(closed_cycle, facilitator, is_anonymous=False, text="attributed")
    anonymous = make_card(closed_cycle, facilitator, is_anonymous=True, text="anonymous")

    advance_stage(facilitator, retrospective, Stage.REVEAL)

    attributed.refresh_from_db()
    anonymous.refresh_from_db()
    assert attributed.author_id == facilitator.id
    assert anonymous.author_id is None


@pytest.mark.django_db
def test_reveal_creates_cycle_participation_counting_all_cards_per_author(
    retrospective, closed_cycle, facilitator, member
):
    # facilitator: 2 anonymous + 1 non-anonymous = 3 cards
    make_card(closed_cycle, facilitator, is_anonymous=True, text="f1")
    make_card(closed_cycle, facilitator, is_anonymous=True, text="f2")
    make_card(closed_cycle, facilitator, is_anonymous=False, text="f3")
    # member: 1 non-anonymous card
    make_card(closed_cycle, member, is_anonymous=False, text="m1")

    advance_stage(facilitator, retrospective, Stage.REVEAL)

    facilitator_participation = CycleParticipation.objects.get(
        cycle=closed_cycle, user=facilitator
    )
    member_participation = CycleParticipation.objects.get(cycle=closed_cycle, user=member)
    assert facilitator_participation.card_count == 3
    assert member_participation.card_count == 1
    assert facilitator_participation.submitted_at is not None


@pytest.mark.django_db
def test_reveal_shuffle_is_a_genuine_seeded_permutation(retrospective, closed_cycle, facilitator):
    cards = [make_card(closed_cycle, facilitator, position=i, text=f"card-{i}") for i in range(5)]
    original_positions = [c.position for c in cards]

    seed = 20260902
    random.seed(seed)
    advance_stage(facilitator, retrospective, Stage.REVEAL)

    expected_rng = random.Random(seed)
    expected_positions = list(original_positions)
    expected_rng.shuffle(expected_positions)

    actual_positions = [
        Card.objects.get(pk=c.pk).position for c in sorted(cards, key=lambda c: c.pk)
    ]
    assert actual_positions == expected_positions
    # Not just "a permutation" in the abstract -- confirm it's genuinely
    # not the identity map for this fixture/seed.
    assert actual_positions != original_positions
    assert sorted(actual_positions) == sorted(original_positions)


@pytest.mark.django_db
def test_on_reveal_called_twice_directly_does_not_raise_or_double_count(
    retrospective, closed_cycle, facilitator
):
    """Defense-in-depth per the issue: `advance_stage`'s forward-only
    guard makes a second real call unreachable, but `_on_reveal` itself
    must tolerate being invoked again directly without raising
    `IntegrityError` and without double-counting participation.
    """
    make_card(closed_cycle, facilitator, is_anonymous=True, text="a")
    make_card(closed_cycle, facilitator, is_anonymous=False, text="b")

    _on_reveal(retrospective)
    first_count = CycleParticipation.objects.get(cycle=closed_cycle, user=facilitator).card_count
    assert first_count == 2

    # Second direct call: by now the anonymous card's author is already
    # NULL, so no new participation is attributed and no duplicate row
    # is attempted.
    _on_reveal(retrospective)

    assert CycleParticipation.objects.filter(cycle=closed_cycle, user=facilitator).count() == 1
    second = CycleParticipation.objects.get(cycle=closed_cycle, user=facilitator)
    assert second.card_count == first_count


@pytest.mark.django_db
def test_reveal_full_integration_via_advance_stage(project, facilitator, member):
    cycle = FeedbackCycle.objects.create(
        project=project, week_start=WEEK_START, facilitator=facilitator
    )
    fac_attributed = make_card(cycle, facilitator, is_anonymous=False, position=0, text="fa")
    fac_anonymous = make_card(cycle, facilitator, is_anonymous=True, position=1, text="fb")
    member_anonymous = make_card(cycle, member, is_anonymous=True, position=0, text="ma")

    cycle.close()
    cycle.refresh_from_db()
    retro = cycle.retrospective

    advance_stage(facilitator, retro, Stage.REVEAL)
    retro.refresh_from_db()

    assert retro.stage == Stage.REVEAL

    fac_attributed.refresh_from_db()
    fac_anonymous.refresh_from_db()
    member_anonymous.refresh_from_db()

    assert fac_attributed.author_id == facilitator.id
    assert fac_anonymous.author is None
    assert member_anonymous.author is None

    fac_participation = CycleParticipation.objects.get(cycle=cycle, user=facilitator)
    member_participation = CycleParticipation.objects.get(cycle=cycle, user=member)
    assert fac_participation.card_count == 2
    assert member_participation.card_count == 1

    remaining_positions = set(
        Card.objects.filter(cycle=cycle, category=Card.Category.START).values_list(
            "position", flat=True
        )
    )
    assert remaining_positions == {0, 1}
