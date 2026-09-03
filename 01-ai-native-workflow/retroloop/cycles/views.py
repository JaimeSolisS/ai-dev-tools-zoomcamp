"""Views for creating and closing a `FeedbackCycle`, and for the
Start/Stop/Continue card board (issue #8).

Issue #7 constraints: no inline `if request.user == ...` checks here --
authorization goes through `projects.permissions.can_create_cycle` /
`can_close_cycle`. The one-COLLECTING-cycle-per-project rule is enforced
by the DB (see `cycles/models.py`); this view's job is only to catch the
resulting `IntegrityError` and turn it into a clean form error instead of
a 500.

Issue #8 card views follow the same authorization split throughout:

- Board/list/create act on a *cycle* the caller reached by ID, so a
  non-member gets 403 (mirrors `cycle_create`/`cycle_close` above) --
  membership is checked with `can_view_project` directly, kept separate
  from the closed-cycle check so a closed cycle produces a clean form
  error instead of a 403 for a member who is otherwise allowed to be
  here.
- Edit/delete act on a *card* the caller reached by ID. Per the issue's
  explicit edge case, guessing another member's card ID must return 404,
  not 403 -- it must not confirm the card exists. So these two look the
  card up scoped to `author=request.user` up front: a non-member's guess,
  another member's card, and an already-deleted card are all
  indistinguishable 404s.
"""

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from cycles.forms import CardForm, FeedbackCycleForm
from cycles.models import Card, FeedbackCycle
from projects.models import Project
from projects.permissions import (
    can_add_card,
    can_close_cycle,
    can_create_cycle,
    can_delete_card,
    can_edit_card,
    can_view_project,
)


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


def _next_position(cycle, category):
    """Next integer position within `(cycle, category)`, creation-order
    only -- see `cycles.models.Card`'s docstring. Counts every card in the
    category regardless of author: positions are a property of the
    category's card sequence for later (reveal/cluster) rendering, not a
    per-member counter, even though a member's own screen only ever shows
    their own cards."""
    return Card.objects.filter(cycle=cycle, category=category).count()


@login_required
def card_board(request, cycle_pk):
    """GET /cycles/<cycle_pk>/board/ -- three-column Start/Stop/Continue
    screen for the requesting member's own cards on this cycle. Non-member
    gets 403 (mirrors `cycle_create`/`cycle_close`'s pattern); the
    queryset below is what actually keeps another member's cards off the
    page -- filtered here, never in the template, per AGENTS.md."""
    cycle = get_object_or_404(FeedbackCycle, pk=cycle_pk)
    if not can_view_project(request.user, cycle.project):
        return HttpResponseForbidden()

    own_cards = Card.objects.filter(cycle=cycle, author=request.user)
    columns = [
        (value, label, own_cards.filter(category=value)) for value, label in Card.Category.choices
    ]
    context = {
        "cycle": cycle,
        "project": cycle.project,
        "columns": columns,
        "form": CardForm(),
    }
    return render(request, "cycles/board.html", context)


@login_required
@require_POST
def card_create(request, cycle_pk):
    """POST /cycles/<cycle_pk>/cards/ -- creates a card in the category
    named by the `category` POST field. Returns just the new card's
    fragment (for `hx-swap="beforeend"` into that category's column) on
    success; on rejection (non-member, closed cycle, invalid text) it
    never creates a row and never 500s."""
    cycle = get_object_or_404(FeedbackCycle, pk=cycle_pk)
    if not can_view_project(request.user, cycle.project):
        return HttpResponseForbidden()

    category = request.POST.get("category")
    if category not in Card.Category.values:
        return HttpResponse("Unknown category.", status=400)

    form = CardForm(request.POST)

    if not can_add_card(request.user, cycle):
        # Membership already passed above, so the only way `can_add_card`
        # is False here is the COLLECTING-status check -- a clean form
        # error, never a 403 and never a 500.
        form.add_error(None, "This cycle is closed -- new cards can't be added.")
        return render(
            request,
            "cycles/_card_form_errors.html",
            {"form": form, "category": category},
            status=200,
        )

    if form.is_valid():
        with transaction.atomic():
            card = form.save(commit=False)
            card.cycle = cycle
            card.category = category
            card.author = request.user
            card.position = _next_position(cycle, category)
            card.save()
        return render(request, "cycles/_card.html", {"card": card})

    return render(
        request,
        "cycles/_card_form_errors.html",
        {"form": form, "category": category},
        status=200,
    )


def _body_data(request):
    """Django only populates `request.POST` for POST requests -- a PUT
    body (used by the edit form's `hx-put`) has to be parsed by hand.
    HTMX submits form-encoded bodies regardless of verb, so `QueryDict`
    handles both."""
    if request.method == "POST":
        return request.POST
    return QueryDict(request.body)


def _own_card_or_404(user, pk):
    """Scopes the lookup to `author=user` up front so a non-member's
    guess, another member's card, and an already-deleted card are all the
    same indistinguishable 404 -- per issue #8's explicit "don't leak
    existence" edge case."""
    return get_object_or_404(Card, pk=pk, author=user)


@login_required
@require_http_methods(["POST", "PUT"])
def card_edit(request, pk):
    """POST/PUT /cards/<pk>/ -- edits the requesting member's own card.
    Returns the updated card's fragment for an `outerHTML` swap on
    success; a closed cycle or invalid text re-renders the same fragment
    with the error shown inline, still scoped to that one card."""
    card = _own_card_or_404(request.user, pk)

    if not can_edit_card(request.user, card):
        # `_own_card_or_404` already guarantees `card.author == request.user`,
        # so the only way this predicate is False here is the
        # COLLECTING-status check -- a clean form error, not a 403/404.
        # `add_error` requires a *bound* form (it lazily triggers
        # `full_clean` to populate `cleaned_data`) -- bind it to the
        # submitted data rather than leaving it unbound.
        form = CardForm(_body_data(request), instance=card)
        form.is_valid()
        form.add_error(None, "This cycle is closed -- cards can no longer be edited.")
        return render(request, "cycles/_card.html", {"card": card, "form": form}, status=200)

    form = CardForm(_body_data(request), instance=card)
    if form.is_valid():
        form.save()
        return render(request, "cycles/_card.html", {"card": card})

    return render(request, "cycles/_card.html", {"card": card, "form": form}, status=200)


@login_required
@require_http_methods(["DELETE"])
def card_delete(request, pk):
    """DELETE /cards/<pk>/ -- deletes the requesting member's own card and
    returns an empty 200 (the client removes the card element itself). A
    double-submit on an already-deleted card's ID hits the same
    `author=user` scoped lookup and 404s -- it never assumes the row still
    exists."""
    card = _own_card_or_404(request.user, pk)

    if not can_delete_card(request.user, card):
        return HttpResponseForbidden()

    card.delete()
    return HttpResponse(status=200)
