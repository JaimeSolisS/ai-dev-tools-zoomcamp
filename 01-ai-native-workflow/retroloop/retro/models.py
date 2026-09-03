"""`Retrospective` model. See issue #9 and `_docs/architecture.md`'s
"Retrospective" and "Stage machine" sections.

Only the fields issue #9 needs are here (`Cluster`, `Vote`, `Note`,
`Decision`, `ActionItem` from architecture.md's fuller schema are later
issues' work -- #14/#15/#16/#22 -- and are out of this issue's scope).

`Retrospective.stage` is never assigned outside `retro.services.advance_stage`
-- see that module's docstring for why. This file defines the shape only.
"""

from django.db import models


class Retrospective(models.Model):
    class Stage(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        REVEAL = "REVEAL", "Reveal"
        CLUSTER = "CLUSTER", "Cluster"
        VOTE = "VOTE", "Vote"
        DISCUSS = "DISCUSS", "Discuss"
        COMPLETE = "COMPLETE", "Complete"

    cycle = models.OneToOneField(
        "cycles.FeedbackCycle", on_delete=models.CASCADE, related_name="retrospective"
    )
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.DRAFT)
    # Null until DRAFT -> REVEAL / DISCUSS -> COMPLETE respectively; set by
    # retro.services.advance_stage, never by hand.
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # The entire board-sync mechanism (see #11) -- bumped by every
    # mutating transaction via retro.services.bump_version, not only
    # stage changes.
    version = models.IntegerField(default=1)

    # Set for real by retro.services._on_freeze_clusters (CLUSTER -> VOTE):
    # once True, future move/rename endpoints (#12/#14) must reject
    # cluster/card moves. The Cluster model doesn't exist yet, so this is
    # a flag those endpoints will check rather than an enforced
    # constraint today.
    clusters_frozen = models.BooleanField(default=False)
    # Set for real by retro.services._on_discuss (VOTE -> DISCUSS): #11's
    # board-state serializer reads this to stop omitting vote totals from
    # the payload (architecture.md: "Vote totals are omitted... not
    # hidden in the client").
    votes_revealed = models.BooleanField(default=False)

    def __str__(self):
        return f"Retrospective for {self.cycle} ({self.stage})"
