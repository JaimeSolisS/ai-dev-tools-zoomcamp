"""Project and Membership models. See issue #5 and
`_docs/architecture.md`'s "Identity and membership" section.

Design decision (issue #5): `Project.owner` always has a matching
`Membership` row with role FACILITATOR -- created atomically alongside the
Project in `projects.views.project_create`. `owner` is a pointer to *which*
FACILITATOR member holds the owner-only powers (token rotation), not a
separate identity from membership.
"""

import uuid

from django.conf import settings
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=200)
    # PROTECT: a project must never be silently orphaned by a user
    # deletion. There is no user-deletion flow in this app yet, but the
    # constraint documents the intent regardless.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_projects",
    )
    # UUID, not a short slug: the whole point is an unguessable link, per
    # architecture.md. Not settable by the client -- only ever assigned by
    # `default=uuid.uuid4` on create or by the rotation view.
    join_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        FACILITATOR = "FACILITATOR", "Facilitator"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")
        ]

    def __str__(self):
        return f"{self.user} @ {self.project} ({self.role})"
