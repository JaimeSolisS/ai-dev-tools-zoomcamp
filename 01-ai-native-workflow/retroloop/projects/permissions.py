"""Authorization predicates for `Project`, `Membership`, and
`cycles.FeedbackCycle`.

Per AGENTS.md: "All authorization lives in `projects/permissions.py` as
predicate functions taking a user and a domain object, never as inline
`if request.user ==` checks in views."

Scope (issue #6): predicates over the models #5 built (`Project`,
`Membership`). Issue #7 adds `can_create_cycle`/`can_close_cycle` for
`cycles.FeedbackCycle` here too, per AGENTS.md's instruction to keep this
module centralized regardless of which app a model lives in.
`Card`/`Retrospective.stage` predicates are deferred to #8/#9/#30.

Every predicate here returns `False` for `AnonymousUser` and for a user
with no (or a deleted) `Membership` row -- it never raises for those
cases. Callers should not need to check `is_authenticated` first.
"""


def can_view_project(user, project):
    """True iff `user` has a Membership row on `project` (any role)."""
    if not user.is_authenticated:
        return False
    return project.memberships.filter(user=user).exists()


def can_rotate_join_token(user, project):
    """True only for `project.owner` -- not any facilitator."""
    if not user.is_authenticated:
        return False
    return project.owner_id == user.id


def can_view_membership_list(user, project):
    """Same rule as `can_view_project`, kept as its own predicate so a
    future change to one rule doesn't silently change the other."""
    if not user.is_authenticated:
        return False
    return project.memberships.filter(user=user).exists()


def can_create_cycle(user, project):
    """True iff `user` has a Membership row on `project` (any role) --
    issue #7: any member, not only `FACILITATOR`-role members, can open a
    cycle."""
    if not user.is_authenticated:
        return False
    return project.memberships.filter(user=user).exists()


def can_close_cycle(user, cycle):
    """True only for `cycle.facilitator` -- not the project owner, not
    another facilitator, not the cycle's own creator if they aren't its
    facilitator. The facilitator role is per cycle, not per project (see
    architecture.md), so this checks the FK directly rather than
    `Membership.role`."""
    if not user.is_authenticated:
        return False
    return cycle.facilitator_id == user.id
