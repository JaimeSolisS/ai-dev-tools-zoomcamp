"""Views for `retro/`. Issue #9 ships one endpoint: triggering
`advance_stage`. The polished board UI (state polling, per-stage
rendering) is #11-#14's job -- this is deliberately a plain POST that
redirects back to the project page.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from retro.models import Retrospective
from retro.services import STAGE_ORDER, advance_stage


@login_required
@require_POST
def retrospective_advance(request, pk):
    """POST /retros/<pk>/advance/ -- advances the retrospective to its
    immediate next stage in `STAGE_ORDER`. Facilitator-only, enforced by
    `advance_stage` (via `can_advance_stage`) -- a non-facilitator gets a
    403, never a silent no-op. `stage == COMPLETE` (no next stage) also
    gets a 403 rather than a 500.
    """
    retrospective = get_object_or_404(Retrospective, pk=pk)

    try:
        current_index = STAGE_ORDER.index(retrospective.stage)
    except ValueError:
        current_index = -1
    if current_index == -1 or current_index + 1 >= len(STAGE_ORDER):
        return HttpResponseForbidden("This retrospective cannot be advanced further.")
    target_stage = STAGE_ORDER[current_index + 1]

    try:
        advance_stage(request.user, retrospective, target_stage)
    except PermissionDenied:
        return HttpResponseForbidden()
    except ValueError as exc:
        return HttpResponseForbidden(str(exc))

    return redirect("project-detail", pk=retrospective.cycle.project_id)
