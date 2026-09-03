import calendar as calendar_module
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from .forms import ChoreForm, MemberCreateForm
from .models import Chore, CompletionHistory, User

CALENDAR_MAX_PER_DAY = 3
WEEK_MAX_PER_DAY = 6


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_admin

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied


def household_chores(user):
    return Chore.objects.filter(household=user.household)


# --- Calendar -----------------------------------------------------------


@login_required
def calendar_redirect(request):
    today = timezone.localdate()
    return redirect("calendar_month", year=today.year, month=today.month)


def _group_chores_by_day(chores, max_per_day):
    by_day = {}
    for chore in chores:
        by_day.setdefault(chore.due_date, []).append(chore)
    grouped = {}
    for day, items in by_day.items():
        items.sort(key=lambda c: c.title)
        grouped[day] = {
            "visible": items[:max_per_day],
            "overflow_count": max(0, len(items) - max_per_day),
        }
    return grouped


@login_required
def calendar_month(request, year, month):
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar_module.monthrange(year, month)[1])

    chores = household_chores(request.user).filter(
        due_date__gte=first_day, due_date__lte=last_day
    ).prefetch_related("assignees")
    grouped = _group_chores_by_day(chores, CALENDAR_MAX_PER_DAY)

    cal = calendar_module.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    prev_month = (first_day - timedelta(days=1)).replace(day=1)
    next_month = (last_day + timedelta(days=1))

    overdue = household_chores(request.user).filter(
        due_date__lt=timezone.localdate()
    ).exclude(status=Chore.Status.DONE).order_by("due_date")

    return render(
        request,
        "chores/calendar_month.html",
        {
            "weeks": weeks,
            "grouped": grouped,
            "month": first_day,
            "today": timezone.localdate(),
            "prev_year": prev_month.year,
            "prev_month": prev_month.month,
            "next_year": next_month.year,
            "next_month": next_month.month,
            "overdue_chores": overdue,
            "current_iso_year": timezone.localdate().isocalendar().year,
            "current_iso_week": timezone.localdate().isocalendar().week,
        },
    )


@login_required
def calendar_week(request, year, week):
    monday = date.fromisocalendar(year, week, 1)
    days = [monday + timedelta(days=i) for i in range(7)]
    last_day = days[-1]

    chores = household_chores(request.user).filter(
        due_date__gte=monday, due_date__lte=last_day
    ).prefetch_related("assignees")
    grouped = _group_chores_by_day(chores, WEEK_MAX_PER_DAY)

    prev_week = monday - timedelta(days=7)
    next_week = monday + timedelta(days=7)

    overdue = household_chores(request.user).filter(
        due_date__lt=timezone.localdate()
    ).exclude(status=Chore.Status.DONE).order_by("due_date")

    return render(
        request,
        "chores/calendar_week.html",
        {
            "days": days,
            "grouped": grouped,
            "today": timezone.localdate(),
            "prev_year": prev_week.isocalendar().year,
            "prev_week": prev_week.isocalendar().week,
            "next_year": next_week.isocalendar().year,
            "next_week": next_week.isocalendar().week,
            "overdue_chores": overdue,
            "current_year": timezone.localdate().year,
            "current_month": timezone.localdate().month,
        },
    )


@login_required
def day_detail(request, year, month, day):
    the_date = date(year, month, day)
    chores = household_chores(request.user).filter(due_date=the_date).prefetch_related(
        "assignees"
    ).order_by("title")
    return render(
        request, "chores/day_detail.html", {"date": the_date, "chores": chores}
    )


# --- Chores ---------------------------------------------------------------


@login_required
def chore_create(request):
    user = request.user
    if request.method == "POST":
        form = ChoreForm(request.POST, user=user)
        if form.is_valid():
            chore = form.save(commit=False)
            chore.household = user.household
            chore.created_by = user
            chore.status = Chore.Status.PENDING
            chore.save()
            chore.assignees.set(form.cleaned_data["assignees"])
            messages.success(request, "Chore created.")
            return redirect("chore_detail", pk=chore.pk)
    else:
        form = ChoreForm(user=user)
    return render(request, "chores/chore_form.html", {"form": form, "editing": False})


@login_required
def chore_detail(request, pk):
    chore = get_object_or_404(household_chores(request.user), pk=pk)
    is_assignee = chore.assignees.filter(pk=request.user.pk).exists()
    context = {
        "chore": chore,
        "can_claim": chore.can_be_claimed_by(request.user),
        "is_assignee": is_assignee,
    }
    return render(request, "chores/chore_detail.html", context)


@login_required
def chore_edit(request, pk):
    user = request.user
    if not user.is_admin:
        raise PermissionDenied
    chore = get_object_or_404(household_chores(user), pk=pk)
    if not chore.can_be_edited_by_admin():
        messages.error(request, "Done chores are locked and cannot be edited.")
        return redirect("chore_detail", pk=chore.pk)

    if request.method == "POST":
        form = ChoreForm(request.POST, instance=chore, user=user, editing=True)
        if form.is_valid():
            form.save()
            chore.assignees.set(form.cleaned_data["assignees"])
            messages.success(request, "Chore updated.")
            return redirect("chore_detail", pk=chore.pk)
    else:
        form = ChoreForm(instance=chore, user=user, editing=True)
    return render(
        request, "chores/chore_form.html", {"form": form, "editing": True, "chore": chore}
    )


@login_required
def chore_claim(request, pk):
    if request.method != "POST":
        raise PermissionDenied
    chore = get_object_or_404(household_chores(request.user), pk=pk)
    try:
        chore.claim(request.user)
        messages.success(request, "Chore claimed.")
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    return redirect("chore_detail", pk=chore.pk)


@login_required
def chore_status(request, pk):
    if request.method != "POST":
        raise PermissionDenied
    chore = get_object_or_404(household_chores(request.user), pk=pk)
    new_status = request.POST.get("status")
    try:
        chore.transition_status(request.user, new_status)
        messages.success(request, "Status updated.")
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("chore_detail", pk=chore.pk)


# --- Completion history -----------------------------------------------


class CompletionHistoryView(LoginRequiredMixin, ListView):
    template_name = "chores/history.html"
    context_object_name = "records"

    def get_queryset(self):
        return (
            CompletionHistory.objects.filter(chore__household=self.request.user.household)
            .select_related("chore")
            .order_by("-completed_at")
        )


# --- Household admin: member management --------------------------------


class MemberListView(AdminRequiredMixin, ListView):
    template_name = "chores/member_list.html"
    context_object_name = "members"

    def get_queryset(self):
        return User.objects.filter(
            household=self.request.user.household, is_active=True
        ).order_by("display_name")


class MemberCreateView(AdminRequiredMixin, View):
    def get(self, request):
        return render(request, "chores/member_form.html", {"form": MemberCreateForm()})

    def post(self, request):
        form = MemberCreateForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            user.display_name = form.cleaned_data["display_name"]
            user.role = User.Role.MEMBER
            user.household = request.user.household
            user.save()
            messages.success(request, f"Member {user.display_name} created.")
            return redirect("member_list")
        return render(request, "chores/member_form.html", {"form": form})


class MemberRemoveView(AdminRequiredMixin, View):
    def post(self, request, pk):
        member = get_object_or_404(
            User, pk=pk, household=request.user.household, role=User.Role.MEMBER
        )
        member.is_active = False
        member.save(update_fields=["is_active"])

        # Unfinished chores assigned to them become unassigned.
        unfinished = Chore.objects.filter(
            household=request.user.household, assignees=member
        ).exclude(status=Chore.Status.DONE)
        for chore in unfinished:
            chore.assignees.remove(member)

        messages.success(request, f"{member.display_name} removed.")
        return redirect("member_list")
