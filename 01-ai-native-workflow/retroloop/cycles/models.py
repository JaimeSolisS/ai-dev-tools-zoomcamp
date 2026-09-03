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
from django.db import models, transaction
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
        `projects.permissions.can_close_cycle` before calling this.

        Issue #9: also creates this cycle's `Retrospective` row
        (`stage=DRAFT`, `version=1`), in the same transaction as the
        status write, via `get_or_create` -- so a race between two
        concurrent `close()` calls (or a caller ignoring the early-return
        above) can never create a second row or reset an in-progress
        retrospective. A `Retrospective` existing is proof its cycle is
        `CLOSED`; `retro.services.advance_stage` relies on this and does
        not re-check cycle status itself.
        """
        if self.status == self.Status.CLOSED:
            return
        # Local import: retro.models has no import-time dependency on
        # cycles.models (it references "cycles.FeedbackCycle" as a
        # string FK), but importing it at module level here would make
        # cycles depend on retro at Django app-loading time -- keep the
        # dependency local to where it's actually used.
        from retro.models import Retrospective

        with transaction.atomic():
            self.status = self.Status.CLOSED
            self.closes_at = timezone.now()
            self.save(update_fields=["status", "closes_at"])
            Retrospective.objects.get_or_create(
                cycle=self,
                defaults={"stage": Retrospective.Stage.DRAFT, "version": 1},
            )


class Card(models.Model):
    """A single Start/Stop/Continue card. See issue #8 and
    `_docs/architecture.md`'s "Feedback collection" section.

    Design decisions (issue #8):

    - `author` is nullable **from the start**, not added later -- #10's
      reveal step nulls it out for anonymous cards, and designing it
      non-nullable here would force a breaking migration when that lands.
    - `is_anonymous` is stored here but has no effect in this task's views
      -- a member already only ever sees their own cards on this screen
      (queryset filter in `cycles.views`), so there's no one to hide the
      author from yet. It's read by #10's reveal to decide which cards get
      `author` nulled.
    - `position` is the next integer within `(cycle, category)` for that
      member's cards, assigned by the view at creation time -- creation
      order only, not user-reorderable in this task (see #14).
    - Create/edit/delete are all gated on `cycle.status == COLLECTING` --
      enforced by the `can_add_card`/`can_edit_card`/`can_delete_card`
      predicates in `projects/permissions.py`, never inline in the view.
    """

    class Category(models.TextChoices):
        START = "START", "Start"
        STOP = "STOP", "Stop"
        CONTINUE = "CONTINUE", "Continue"

    cycle = models.ForeignKey(FeedbackCycle, on_delete=models.CASCADE, related_name="cards")
    category = models.CharField(max_length=20, choices=Category.choices)
    text = models.CharField(max_length=500)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cards",
    )
    is_anonymous = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category", "position"]

    def __str__(self):
        return f"{self.category}: {self.text[:40]}"
