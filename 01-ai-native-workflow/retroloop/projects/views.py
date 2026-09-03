"""Views for creating/listing/viewing projects, joining via link, and
rotating the join token.

Issue #5 constraints: no `if request.user == project.owner` scattered
through views. Authorization checks call into `projects/permissions.py`
(#6) rather than being inlined here.
"""

import uuid

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from projects.forms import ProjectForm
from projects.models import Membership, Project
from projects.permissions import can_rotate_join_token


def _visible_to(user):
    """Projects `user` has a Membership row on. Every view that shows or
    accepts a project id filters through this queryset so a non-member
    gets 404 (not 403) -- the response never reveals whether the project
    exists, per issue #5. This mirrors `can_view_project` as a queryset
    rather than calling the predicate row-by-row, since these views need
    "which projects" not "can I see this one" -- see #6."""
    return Project.objects.filter(memberships__user=user)


@login_required
def project_list(request):
    projects = _visible_to(request.user)
    return render(request, "projects/list.html", {"projects": projects})


@login_required
def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                project = form.save(commit=False)
                project.owner = request.user
                project.save()
                Membership.objects.create(
                    project=project,
                    user=request.user,
                    role=Membership.Role.FACILITATOR,
                )
            return redirect("project-detail", pk=project.pk)
    else:
        form = ProjectForm()
    return render(request, "projects/create.html", {"form": form})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(_visible_to(request.user), pk=pk)
    return render(request, "projects/detail.html", {"project": project})


@login_required
def join(request, token):
    """GET /join/<token>/. `login_required` handles the logged-out case:
    redirect to login with `?next=`, then Django's standard post-login
    redirect chain lands back here and the join completes.

    `get_or_create` makes "already a member" a no-op instead of an
    IntegrityError -- covers both a returning member and the owner
    visiting their own link (the owner already has a FACILITATOR row from
    project creation)."""
    project = get_object_or_404(Project, join_token=token)
    Membership.objects.get_or_create(
        project=project,
        user=request.user,
        defaults={"role": Membership.Role.MEMBER},
    )
    return redirect("project-detail", pk=project.pk)


@login_required
@require_POST
def rotate_token(request, pk):
    """POST /projects/<id>/rotate-token/. Owner-only: a non-member gets
    404 (via `_visible_to`), a member who isn't the owner gets 403."""
    project = get_object_or_404(_visible_to(request.user), pk=pk)
    if not can_rotate_join_token(request.user, project):
        return HttpResponseForbidden()

    project.join_token = uuid.uuid4()
    project.save(update_fields=["join_token"])
    return redirect("project-detail", pk=project.pk)
