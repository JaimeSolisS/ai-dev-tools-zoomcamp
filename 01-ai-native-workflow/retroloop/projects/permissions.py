"""Authorization predicates for `Project` and `Membership`.

Per AGENTS.md: "All authorization lives in `projects/permissions.py` as
predicate functions taking a user and a domain object, never as inline
`if request.user ==` checks in views."

Scope (issue #6): only predicates the models #5 built (`Project`,
`Membership`) can support. `Card`/`Retrospective.stage`/cycle-facilitator
predicates are deferred to #7-#9/#30 -- see issue #6 for the full
breakdown.

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
