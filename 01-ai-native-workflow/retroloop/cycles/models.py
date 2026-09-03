"""FeedbackCycle model. See issue #7 and `_docs/architecture.md`'s
"Feedback collection" section.

Design decision (issue #7): only one COLLECTING cycle per project is
allowed at a time, and this is enforced at the database with a partial
unique index (`UniqueConstraint` + `condition`), not application logic
alone. Two requests racing past the app-level check both attempt to
INSERT a COLLECTING row for the same project; the database allows only
the first, and the second raises `IntegrityError`, which
`cycles.views.cycle_create` catches and turns into a clean form error
instead of a 500.

The facilitator role is per cycle, not per project (see architecture.md):
`Membership.role` is only the default suggestion on the create form, never
a constraint on who can be assigned.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class FeedbackCycle(models.Model):
    class Status(models.TextChoices):
        COLLECTING = "COLLECTING", "Collecting"
        CLOSED = "CLOSED", "Closed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="cycles"
    )
    # Free input on the create form -- not derived from `opens_at`'s date,
    # since the day a cycle is opened and the week it covers can differ.
    week_start = models.DateField()
    opens_at = models.DateTimeField(auto_now_add=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    facilitator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="facilitated_cycles",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COLLECTING)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(status="COLLECTING"),
                name="one_collecting_cycle_per_project",
            )
        ]

    def __str__(self):
        return f"{self.project} -- week of {self.week_start} ({self.status})"

    def close(self):
        """Idempotent: closing an already-CLOSED cycle is a no-op -- does
        not re-stamp `closes_at` and does not error. Callers (views) are
        responsible for the authorization check via
        `projects.permissions.can_close_cycle` before calling this."""
        if self.status == self.Status.CLOSED:
            return
        self.status = self.Status.CLOSED
        self.closes_at = timezone.now()
        self.save(update_fields=["status", "closes_at"])
