"""Stage-transition service for `Retrospective`. See issue #9 and
`_docs/architecture.md`'s "Stage machine" section.

`advance_stage()` is the single place `Retrospective.stage` is ever
assigned. No view, form, or admin action may set `retrospective.stage =
...` directly -- per AGENTS.md: "Stage changes go through
`advance_stage()` only. Forward-only, facilitator-only, each transition's
side effects in the same transaction."

Hook structure for future issues (#10, #14, #16, #22): `TRANSITIONS` is a
module-level dict keyed by `(from_stage, to_stage)` -> a callable taking
one argument, the `Retrospective` instance (already locked via
`select_for_update()`, still at the OLD stage, inside the same
`transaction.atomic()` block `advance_stage` runs in). A later issue
plugs in real behaviour by replacing an existing hook function's body --
it never adds a new entry to `TRANSITIONS` or touches `advance_stage`
itself. `_on_reveal` (DRAFT -> REVEAL) is issue #10's target; `_on_cluster`
(REVEAL -> CLUSTER) is issue #22's.
"""

import random

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from cycles.models import Card, CycleParticipation
from projects.permissions import can_advance_stage
from retro.models import Retrospective

# Fixed sequence of the stage machine (architecture.md: "DRAFT -> REVEAL ->
# CLUSTER -> VOTE -> DISCUSS -> COMPLETE"). `advance_stage` only accepts a
# `target_stage` that is the immediate successor of the current stage in
# this list -- COMPLETE has no successor, so it is terminal.
STAGE_ORDER = [
    Retrospective.Stage.DRAFT,
    Retrospective.Stage.REVEAL,
    Retrospective.Stage.CLUSTER,
    Retrospective.Stage.VOTE,
    Retrospective.Stage.DISCUSS,
    Retrospective.Stage.COMPLETE,
]


def bump_version(retrospective, *, extra_update_fields=None):
    """Increments `Retrospective.version` by 1 and saves.

    Standalone helper (issue #9's explicit constraint) so #12's mutation
    endpoints (card move, cluster rename, vote cast, ...) can bump the
    board-sync counter without going through `advance_stage` -- version
    is bumped by every mutating transaction, not only stage changes.

    `advance_stage` also calls this rather than inlining the increment,
    passing whichever other fields it changed via `extra_update_fields`
    so everything is written in the one `save()` call.

    Callers needing race protection beyond a normal save (e.g. two
    concurrent mutations to the same retrospective) should wrap this in
    their own `transaction.atomic()` + `select_for_update()`, the same
    pattern `advance_stage` uses below.
    """
    retrospective.version += 1
    fields = {"version"}
    if extra_update_fields:
        fields.update(extra_update_fields)
    retrospective.save(update_fields=list(fields))
    return retrospective


def _on_reveal(retrospective):
    """DRAFT -> REVEAL hook. See issue #10 and `_docs/architecture.md`'s
    "anonymity design" section.

    Called with `retrospective` already locked (`select_for_update`) and
    still at stage DRAFT, inside the same `transaction.atomic()` block
    `advance_stage` runs in -- everything below commits atomically with
    the stage write, or the whole transition rolls back. No second
    transaction is opened here.

    Order of operations matters and is fixed:

    1. Compute `CycleParticipation` rows from `Card.author` *before*
       touching it -- one row per distinct non-null author, with
       `card_count` = that author's total card count across the whole
       cycle (anonymous and non-anonymous alike -- participation means
       "did they contribute", not "did they contribute non-anonymously").
       Get this step's ordering wrong and the data is gone, not merely
       delayed: after step 2 there is no way to attribute an anonymous
       card back to its author.
    2. Only then null `Card.author` for cards with `is_anonymous=True`.
       Non-anonymous cards are never touched here -- their `author_id`
       is bit-for-bit unchanged.
    3. Shuffle `Card.position` for *all* cards (anonymous and
       non-anonymous alike), independently within each `(cycle,
       category)` group -- the same scope `position` is already
       assigned in at creation (see `Card.position`'s docstring).
       Shuffling only the anonymous cards was considered and rejected:
       a card whose position looks "shuffled" relative to its
       creation-order siblings would leak `is_anonymous` even after
       `author` is nulled -- a weak signal, but shuffling everyone costs
       nothing and removes it entirely.

    Idempotency: `advance_stage`'s forward-only guard makes a second
    call to this function unreachable in normal operation, but as
    defense-in-depth this function is written to be a safe no-op if
    invoked again directly. Non-anonymous cards keep their `author`
    forever (step 2 only ever touches anonymous ones), so a second call
    would still find those authors and try to recompute their
    `CycleParticipation` row -- step 1 therefore uses `get_or_create`
    keyed on `(cycle, user)` rather than `create`, so an existing row
    from the first call is left untouched (`card_count` is not
    recomputed or incremented) instead of raising. `unique_together` is
    the DB-level backstop for this same guarantee under a race. Step 3
    re-shuffling positions on a hypothetical second call is harmless --
    position order carries no meaning beyond "some shuffled order" once
    reveal has already happened once.

    No audit log, soft-delete, shadow column, admin action, or
    management command is added anywhere that would let anyone
    reconstruct which anonymous card belonged to which user after this
    runs -- per AGENTS.md, anonymous authorship is destroyed here, not
    hidden, and that is irreversible by design.
    """
    cards = list(retrospective.cycle.cards.all())

    # Step 1: compute participation from `author` before nulling anything.
    now = timezone.now()
    card_counts = {}
    for card in cards:
        if card.author_id is not None:
            card_counts[card.author_id] = card_counts.get(card.author_id, 0) + 1

    for user_id, count in card_counts.items():
        CycleParticipation.objects.get_or_create(
            cycle=retrospective.cycle,
            user_id=user_id,
            defaults={"card_count": count, "submitted_at": now},
        )

    # Step 2: null `author` for anonymous cards only.
    anonymous_cards = [card for card in cards if card.is_anonymous]
    for card in anonymous_cards:
        card.author = None
    if anonymous_cards:
        Card.objects.bulk_update(anonymous_cards, ["author"])

    # Step 3: shuffle `position` for every card, independently within
    # each (cycle, category) group.
    by_category = {}
    for card in cards:
        by_category.setdefault(card.category, []).append(card)

    shuffled_cards = []
    for group in by_category.values():
        positions = [card.position for card in group]
        random.shuffle(positions)
        for card, new_position in zip(group, positions):
            card.position = new_position
        shuffled_cards.extend(group)

    if shuffled_cards:
        Card.objects.bulk_update(shuffled_cards, ["position"])


def _on_cluster(retrospective):
    """REVEAL -> CLUSTER hook. No-op reserved for issue #22's
    auto-clustering enqueue; no other issue owns this transition."""


def _on_freeze_clusters(retrospective):
    """CLUSTER -> VOTE hook.

    Freezes cluster membership: once voting starts, cards may no longer
    be moved between clusters and clusters may no longer be renamed. The
    `Cluster` / `Card.cluster` models don't exist yet (#14/#22 build
    them), so this only sets `retrospective.clusters_frozen`, the flag
    those future move/rename endpoints must check. Per issue #9's
    acceptance criteria this only needs to exist and be tested at the
    model/service level, not wired into an endpoint yet.
    """
    retrospective.clusters_frozen = True


def _on_discuss(retrospective):
    """VOTE -> DISCUSS hook.

    Unhides vote totals for real: sets `retrospective.votes_revealed`,
    which #11's board-state serializer reads to stop omitting vote
    totals from the payload (architecture.md: "Vote totals are omitted
    from the API payload... not hidden in the client").

    Does NOT compute the ranked agenda ordering by vote weight -- that
    requires the `Cluster`/`Vote` models, which don't exist in this
    issue's scope (see the comment on issue #9 explaining this
    deviation). #16 owns that computation once those models land.
    """
    retrospective.votes_revealed = True


def _on_complete(retrospective):
    """DISCUSS -> COMPLETE hook.

    The board is locked by relying on `stage == COMPLETE` everywhere a
    future mutation endpoint checks stage -- issue #9's acceptance
    criteria explicitly allows this instead of a separate `locked` flag.
    Documented here per that criterion: any mutation endpoint added by a
    later issue must treat COMPLETE as terminal and reject writes.
    """


TRANSITIONS = {
    (Retrospective.Stage.DRAFT, Retrospective.Stage.REVEAL): _on_reveal,
    (Retrospective.Stage.REVEAL, Retrospective.Stage.CLUSTER): _on_cluster,
    (Retrospective.Stage.CLUSTER, Retrospective.Stage.VOTE): _on_freeze_clusters,
    (Retrospective.Stage.VOTE, Retrospective.Stage.DISCUSS): _on_discuss,
    (Retrospective.Stage.DISCUSS, Retrospective.Stage.COMPLETE): _on_complete,
}


def advance_stage(user, retrospective, target_stage):
    """The single place `Retrospective.stage` is ever assigned.

    Facilitator-only: raises `django.core.exceptions.PermissionDenied` if
    `can_advance_stage(user, retrospective)` is False -- `stage` and
    `version` are left untouched.

    Forward-only, one step at a time: `target_stage` must be the exact
    immediate successor of `retrospective.stage` in `STAGE_ORDER`.
    Skip-ahead, backward, same-stage, and any call once `stage ==
    COMPLETE` all raise `ValueError` and change nothing.

    Locks the row with `select_for_update()` inside `transaction.atomic()`
    before reading `stage`, so two concurrent calls for the same
    retrospective serialize rather than both succeeding off a stale
    in-memory `stage` value -- the second call re-reads the fresh
    (post-first-call) `stage` once the lock is released and is evaluated
    against it.

    The transition's `TRANSITIONS` side-effect callable, if one is
    registered for `(current_stage, target_stage)`, is invoked with the
    locked retrospective -- still at the OLD stage -- inside this same
    transaction, before the stage/version write. If it raises, the whole
    transaction (side effect + stage write) rolls back and nothing
    changes.
    """
    with transaction.atomic():
        retrospective = Retrospective.objects.select_for_update().get(pk=retrospective.pk)

        if not can_advance_stage(user, retrospective):
            raise PermissionDenied("Only the cycle facilitator can advance the retrospective.")

        current_stage = retrospective.stage
        try:
            current_index = STAGE_ORDER.index(current_stage)
        except ValueError:
            current_index = -1

        is_legal = (
            current_index != -1
            and current_index + 1 < len(STAGE_ORDER)
            and STAGE_ORDER[current_index + 1] == target_stage
        )
        if not is_legal:
            raise ValueError(
                f"Cannot advance retrospective from {current_stage} to {target_stage}: "
                "only the exact next stage in the sequence is allowed."
            )

        side_effect = TRANSITIONS.get((current_stage, target_stage))
        if side_effect is not None:
            side_effect(retrospective)

        retrospective.stage = target_stage
        extra_fields = {"stage", "clusters_frozen", "votes_revealed"}
        if target_stage == Retrospective.Stage.REVEAL:
            retrospective.started_at = timezone.now()
            extra_fields.add("started_at")
        if target_stage == Retrospective.Stage.COMPLETE:
            retrospective.completed_at = timezone.now()
            extra_fields.add("completed_at")

        bump_version(retrospective, extra_update_fields=extra_fields)

    return retrospective
