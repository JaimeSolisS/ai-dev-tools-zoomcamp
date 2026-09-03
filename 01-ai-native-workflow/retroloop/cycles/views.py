"""Views for creating and closing a `FeedbackCycle`.

Issue #7 constraints: no inline `if request.user == ...` checks here --
authorization goes through `projects.permissions.can_create_cycle` /
`can_close_cycle`. The one-COLLECTING-cycle-per-project rule is enforced
by the DB (see `cycles/models.py`); this view's job is only to catch the
resulting `IntegrityError` and turn it into a clean form error instead of
a 500.
"""

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cycles.forms import FeedbackCycleForm
from cycles.models import FeedbackCycle
from projects.models import Project
from projects.permissions import can_close_cycle, can_create_cycle


@login_required
def cycle_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_create_cycle(request.user, project):
        return HttpResponseForbidden()

    if request.method == "POST":
        form = FeedbackCycleForm(request.POST, project=project)
        if form.is_valid():
            cycle = form.save(commit=False)
            cycle.project = project
            try:
                with transaction.atomic():
                    cycle.save()
            except IntegrityError:
                # The DB constraint (`one_collecting_cycle_per_project`)
                # is what actually stops a race between two concurrent
                # creates -- this is the clean error the loser sees,
                # never a 500 and never a second COLLECTING row.
                form.add_error(None, "This project already has an open cycle.")
            else:
                return redirect("project-detail", pk=project.pk)
    else:
        form = FeedbackCycleForm(project=project, initial={"facilitator": request.user.pk})

    return render(request, "cycles/create.html", {"form": form, "project": project})


@login_required
@require_POST
def cycle_close(request, pk):
    cycle = get_object_or_404(FeedbackCycle, pk=pk)
    if not can_close_cycle(request.user, cycle):
        return HttpResponseForbidden()

    cycle.close()
    return redirect("project-detail", pk=cycle.project_id)
