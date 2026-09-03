from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import MemberCreateForm
from .models import Category, Chore, ChoreAssignee, CompletionHistory, Household, User


def make_user(username, role, household, **kwargs):
    user = User.objects.create_user(username=username, password="password123", **kwargs)
    user.role = role
    user.household = household
    user.display_name = kwargs.get("display_name", username.title())
    user.save()
    return user


class ModelTestCase(TestCase):
    def setUp(self):
        self.household = Household.objects.create()
        self.admin = make_user("admin1", User.Role.ADMIN, self.household)
        self.member = make_user("member1", User.Role.MEMBER, self.household)
        self.other_member = make_user("member2", User.Role.MEMBER, self.household)
        self.category = Category.objects.create(name="Kitchen")

    def make_chore(self, **kwargs):
        defaults = dict(
            household=self.household,
            title="Test chore",
            due_date=timezone.localdate(),
            category=self.category,
            created_by=self.admin,
        )
        defaults.update(kwargs)
        return Chore.objects.create(**defaults)


class StatusTransitionTests(ModelTestCase):
    def test_member_can_move_pending_to_in_progress(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        chore.transition_status(self.member, Chore.Status.IN_PROGRESS)
        self.assertEqual(chore.status, Chore.Status.IN_PROGRESS)

    def test_member_cannot_skip_illegal_transition(self):
        # Only PENDING -> {IN_PROGRESS, DONE}, DONE -> {PENDING, IN_PROGRESS},
        # IN_PROGRESS -> {DONE}. IN_PROGRESS -> PENDING is not allowed.
        chore = self.make_chore(status=Chore.Status.IN_PROGRESS)
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        with self.assertRaises(PermissionDenied):
            chore.transition_status(self.member, Chore.Status.PENDING)

    def test_member_cannot_change_status_of_chore_not_assigned_to_them(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.other_member)
        with self.assertRaises(PermissionDenied):
            chore.transition_status(self.member, Chore.Status.DONE)

    def test_admin_can_set_any_status_directly(self):
        chore = self.make_chore()
        chore.transition_status(self.admin, Chore.Status.DONE)
        self.assertEqual(chore.status, Chore.Status.DONE)

    def test_marking_done_creates_completion_history(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        chore.transition_status(self.member, Chore.Status.DONE)
        self.assertTrue(CompletionHistory.objects.filter(chore=chore).exists())
        self.assertIsNotNone(chore.completed_at)

    def test_reopening_done_chore_removes_completion_history(self):
        chore = self.make_chore(status=Chore.Status.DONE)
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        CompletionHistory.objects.create(chore=chore, completed_at=timezone.now())

        chore.transition_status(self.member, Chore.Status.PENDING)

        self.assertFalse(CompletionHistory.objects.filter(chore=chore).exists())
        self.assertIsNone(chore.completed_at)

    def test_any_assignee_marking_done_completes_chore_for_everyone(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        ChoreAssignee.objects.create(chore=chore, user=self.other_member)
        chore.transition_status(self.other_member, Chore.Status.DONE)
        self.assertEqual(chore.status, Chore.Status.DONE)

    def test_invalid_status_value_raises(self):
        chore = self.make_chore()
        with self.assertRaises(ValueError):
            chore.transition_status(self.admin, "not_a_status")


class OverdueTests(ModelTestCase):
    def test_past_due_and_not_done_is_overdue(self):
        chore = self.make_chore(due_date=timezone.localdate() - timedelta(days=1))
        self.assertTrue(chore.is_overdue)

    def test_past_due_but_done_is_not_overdue(self):
        chore = self.make_chore(
            due_date=timezone.localdate() - timedelta(days=1), status=Chore.Status.DONE
        )
        self.assertFalse(chore.is_overdue)

    def test_future_due_date_is_not_overdue(self):
        chore = self.make_chore(due_date=timezone.localdate() + timedelta(days=1))
        self.assertFalse(chore.is_overdue)


class ClaimTests(ModelTestCase):
    def test_member_can_claim_unassigned_chore(self):
        chore = self.make_chore()
        chore.claim(self.member)
        self.assertIn(self.member, chore.assignees.all())
        self.assertEqual(chore.status, Chore.Status.PENDING)

    def test_cannot_claim_already_assigned_chore(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.other_member)
        with self.assertRaises(PermissionDenied):
            chore.claim(self.member)

    def test_admin_cannot_claim(self):
        chore = self.make_chore()
        with self.assertRaises(PermissionDenied):
            chore.claim(self.admin)


class EditLockTests(ModelTestCase):
    def test_done_chore_cannot_be_edited(self):
        chore = self.make_chore(status=Chore.Status.DONE)
        self.assertFalse(chore.can_be_edited_by_admin())

    def test_unfinished_chore_can_be_edited(self):
        chore = self.make_chore(status=Chore.Status.IN_PROGRESS)
        self.assertTrue(chore.can_be_edited_by_admin())


class ViewPermissionTests(ModelTestCase):
    def login(self, user):
        self.client.force_login(user)

    def test_member_cannot_access_edit_view(self):
        chore = self.make_chore()
        self.login(self.member)
        response = self.client.get(reverse("chore_edit", args=[chore.pk]))
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_access_member_admin_screens(self):
        self.login(self.member)
        response = self.client.get(reverse("member_list"))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse("member_create"))
        self.assertEqual(response.status_code, 403)

    def test_member_creating_chore_is_forced_to_self_only(self):
        self.login(self.member)
        response = self.client.post(
            reverse("chore_create"),
            {
                "title": "Sweep floor",
                "description": "",
                "due_date": timezone.localdate().isoformat(),
                "category": self.category.pk,
                "assignees": [self.other_member.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        chore = Chore.objects.get(title="Sweep floor")
        self.assertEqual(list(chore.assignees.all()), [self.member])

    def test_admin_can_create_unassigned_chore(self):
        self.login(self.admin)
        response = self.client.post(
            reverse("chore_create"),
            {
                "title": "Take out trash",
                "description": "",
                "due_date": timezone.localdate().isoformat(),
                "category": self.category.pk,
                "assignees": [],
            },
        )
        self.assertEqual(response.status_code, 302)
        chore = Chore.objects.get(title="Take out trash")
        self.assertEqual(chore.assignees.count(), 0)

    def test_creating_chore_with_past_due_date_is_rejected(self):
        self.login(self.admin)
        response = self.client.post(
            reverse("chore_create"),
            {
                "title": "Late chore",
                "description": "",
                "due_date": (timezone.localdate() - timedelta(days=1)).isoformat(),
                "category": self.category.pk,
                "assignees": [],
            },
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertFalse(Chore.objects.filter(title="Late chore").exists())

    def test_no_delete_route_exists(self):
        chore = self.make_chore()
        self.login(self.admin)
        # There is no delete URL name registered at all.
        with self.assertRaises(Exception):
            reverse("chore_delete", args=[chore.pk])


class MemberRemovalTests(ModelTestCase):
    def test_removing_member_deactivates_and_unassigns_unfinished_chores(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        done_chore = self.make_chore(title="Already done", status=Chore.Status.DONE)
        ChoreAssignee.objects.create(chore=done_chore, user=self.member)

        self.client.force_login(self.admin)
        response = self.client.post(reverse("member_remove", args=[self.member.pk]))
        self.assertEqual(response.status_code, 302)

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

        chore.refresh_from_db()
        self.assertNotIn(self.member, chore.assignees.all())

        # Done chores keep their historical assignment.
        self.assertIn(self.member, done_chore.assignees.all())

    def test_removed_member_no_longer_listed_as_active(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("member_remove", args=[self.member.pk]))
        response = self.client.get(reverse("member_list"))
        self.assertNotContains(response, f"<td>{self.member.display_name}</td>")


class ChoreStatusViewTests(ModelTestCase):
    """Status changes routed through the HTTP view, not the model method
    directly — checks the view wires permission errors into a redirect
    with a flash message instead of a 500."""

    def test_get_request_is_rejected(self):
        chore = self.make_chore()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("chore_status", args=[chore.pk]))
        self.assertEqual(response.status_code, 403)

    def test_assignee_marks_chore_done_via_view(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("chore_status", args=[chore.pk]), {"status": Chore.Status.DONE}
        )
        self.assertRedirects(response, reverse("chore_detail", args=[chore.pk]))
        chore.refresh_from_db()
        self.assertEqual(chore.status, Chore.Status.DONE)

    def test_illegal_transition_via_view_does_not_crash_and_shows_error(self):
        chore = self.make_chore(status=Chore.Status.IN_PROGRESS)
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("chore_status", args=[chore.pk]),
            {"status": Chore.Status.PENDING},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        chore.refresh_from_db()
        self.assertEqual(chore.status, Chore.Status.IN_PROGRESS)  # unchanged
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("cannot" in m for m in messages))

    def test_non_assignee_member_cannot_change_status_via_view(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.other_member)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("chore_status", args=[chore.pk]),
            {"status": Chore.Status.DONE},
        )
        self.assertEqual(response.status_code, 302)
        chore.refresh_from_db()
        self.assertEqual(chore.status, Chore.Status.PENDING)  # unchanged


class ChoreClaimViewTests(ModelTestCase):
    def test_get_request_is_rejected(self):
        chore = self.make_chore()
        self.client.force_login(self.member)
        response = self.client.get(reverse("chore_claim", args=[chore.pk]))
        self.assertEqual(response.status_code, 403)

    def test_member_claims_unassigned_chore_via_view(self):
        chore = self.make_chore()
        self.client.force_login(self.member)
        response = self.client.post(reverse("chore_claim", args=[chore.pk]))
        self.assertRedirects(response, reverse("chore_detail", args=[chore.pk]))
        self.assertIn(self.member, chore.assignees.all())

    def test_claiming_already_assigned_chore_via_view_shows_error(self):
        chore = self.make_chore()
        ChoreAssignee.objects.create(chore=chore, user=self.other_member)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("chore_claim", args=[chore.pk]), follow=True
        )
        self.assertNotIn(self.member, chore.assignees.all())
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("claim" in m.lower() for m in messages))


class ChoreEditViewTests(ModelTestCase):
    def test_admin_can_edit_unfinished_chore(self):
        chore = self.make_chore(title="Old title")
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("chore_edit", args=[chore.pk]),
            {
                "title": "New title",
                "description": "Updated",
                "due_date": chore.due_date.isoformat(),
                "category": self.category.pk,
                "assignees": [self.member.pk],
            },
        )
        self.assertRedirects(response, reverse("chore_detail", args=[chore.pk]))
        chore.refresh_from_db()
        self.assertEqual(chore.title, "New title")
        self.assertIn(self.member, chore.assignees.all())

    def test_admin_cannot_open_edit_form_for_done_chore(self):
        chore = self.make_chore(status=Chore.Status.DONE)
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("chore_edit", args=[chore.pk]), follow=True
        )
        self.assertRedirects(response, reverse("chore_detail", args=[chore.pk]))
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("locked" in m.lower() for m in messages))

    def test_admin_can_move_overdue_chore_to_future_date(self):
        chore = self.make_chore(due_date=timezone.localdate() - timedelta(days=3))
        self.client.force_login(self.admin)
        new_due = timezone.localdate() + timedelta(days=2)
        response = self.client.post(
            reverse("chore_edit", args=[chore.pk]),
            {
                "title": chore.title,
                "description": "",
                "due_date": new_due.isoformat(),
                "category": self.category.pk,
                "assignees": [],
            },
        )
        self.assertEqual(response.status_code, 302)
        chore.refresh_from_db()
        self.assertEqual(chore.due_date, new_due)
        self.assertFalse(chore.is_overdue)


class HouseholdIsolationTests(ModelTestCase):
    """Chores and members must never leak across households."""

    def setUp(self):
        super().setUp()
        self.other_household = Household.objects.create()
        self.other_admin = make_user("otheradmin", User.Role.ADMIN, self.other_household)
        self.foreign_chore = self.make_chore(
            household=self.other_household, title="Foreign chore"
        )

    def test_cannot_view_chore_from_another_household(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("chore_detail", args=[self.foreign_chore.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_chore_from_another_household(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("chore_edit", args=[self.foreign_chore.pk]))
        self.assertEqual(response.status_code, 404)

    def test_member_list_only_shows_own_household(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("member_list"))
        self.assertNotContains(response, self.other_admin.display_name)

    def test_calendar_does_not_show_other_households_chores(self):
        self.client.force_login(self.admin)
        today = timezone.localdate()
        response = self.client.get(
            reverse("calendar_month", args=[today.year, today.month])
        )
        self.assertNotContains(response, "Foreign chore")


class CalendarViewTests(ModelTestCase):
    def test_chore_appears_on_its_due_date(self):
        chore = self.make_chore(title="Vacuum living room")
        self.client.force_login(self.admin)
        today = timezone.localdate()
        response = self.client.get(
            reverse("calendar_month", args=[today.year, today.month])
        )
        self.assertContains(response, "Vacuum living room")

    def test_overflow_shows_plus_n_more_link(self):
        today = timezone.localdate()
        for i in range(5):  # CALENDAR_MAX_PER_DAY is 3
            self.make_chore(title=f"Chore {i}", due_date=today)
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("calendar_month", args=[today.year, today.month])
        )
        self.assertContains(response, "+2 more")

    def test_week_view_renders(self):
        today = timezone.localdate()
        iso = today.isocalendar()
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("calendar_week", args=[iso.year, iso.week])
        )
        self.assertEqual(response.status_code, 200)

    def test_overdue_chore_shows_overdue_label_on_calendar(self):
        self.make_chore(
            title="Late trash", due_date=timezone.localdate() - timedelta(days=1)
        )
        self.client.force_login(self.admin)
        today = timezone.localdate()
        response = self.client.get(
            reverse("calendar_month", args=[today.year, today.month])
        )
        self.assertContains(response, "Overdue")


class DayDetailViewTests(ModelTestCase):
    def test_shows_all_chores_for_the_date_including_overflow(self):
        today = timezone.localdate()
        for i in range(5):
            self.make_chore(title=f"Chore {i}", due_date=today)
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("day_detail", args=[today.year, today.month, today.day])
        )
        for i in range(5):
            self.assertContains(response, f"Chore {i}")

    def test_empty_day_shows_no_chores_message(self):
        self.client.force_login(self.admin)
        far_future = timezone.localdate() + timedelta(days=300)
        response = self.client.get(
            reverse(
                "day_detail", args=[far_future.year, far_future.month, far_future.day]
            )
        )
        self.assertContains(response, "No chores on this date")


class CompletionHistoryViewTests(ModelTestCase):
    def test_lists_only_title_and_completion_date(self):
        chore = self.make_chore(title="Mop kitchen")
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        chore.transition_status(self.member, Chore.Status.DONE)

        self.client.force_login(self.member)
        response = self.client.get(reverse("history"))
        self.assertContains(response, "Mop kitchen")

    def test_reopened_chore_disappears_from_history(self):
        chore = self.make_chore(title="Mop kitchen")
        ChoreAssignee.objects.create(chore=chore, user=self.member)
        chore.transition_status(self.member, Chore.Status.DONE)
        chore.transition_status(self.member, Chore.Status.IN_PROGRESS)

        self.client.force_login(self.member)
        response = self.client.get(reverse("history"))
        self.assertContains(response, "Nothing completed yet")

    def test_history_ordered_most_recent_first(self):
        older = self.make_chore(title="Older chore")
        newer = self.make_chore(title="Newer chore")
        older.transition_status(self.admin, Chore.Status.DONE)
        CompletionHistory.objects.filter(chore=older).update(
            completed_at=timezone.now() - timedelta(days=1)
        )
        newer.transition_status(self.admin, Chore.Status.DONE)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("history"))
        content = response.content.decode()
        self.assertLess(content.index("Newer chore"), content.index("Older chore"))


class MemberCreateFormTests(ModelTestCase):
    def test_duplicate_username_rejected(self):
        form = MemberCreateForm(
            data={
                "username": self.member.username,
                "display_name": "Someone Else",
                "password": "password123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_new_member_created_via_view_can_log_in(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("member_create"),
            {
                "username": "newbie",
                "display_name": "Newbie",
                "password": "supersecret123",
            },
        )
        self.client.logout()
        logged_in = self.client.login(username="newbie", password="supersecret123")
        self.assertTrue(logged_in)


class LoginRequiredTests(ModelTestCase):
    def test_anonymous_user_redirected_to_login(self):
        chore = self.make_chore()
        protected_urls = [
            reverse("home"),
            reverse("chore_create"),
            reverse("chore_detail", args=[chore.pk]),
            reverse("history"),
            reverse("member_list"),
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response.url)


class SeedCategoriesCommandTests(TestCase):
    def test_seeds_expected_categories(self):
        call_command("seed_categories")
        names = set(Category.objects.values_list("name", flat=True))
        self.assertEqual(
            names,
            {
                "Cleaning", "Kitchen", "Laundry", "Bathroom", "Bedroom",
                "Shopping", "Trash", "Pet Care", "Other",
            },
        )
        self.assertTrue(Category.objects.filter(is_system=True).count() == 9)

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_categories")
        call_command("seed_categories")
        self.assertEqual(Category.objects.count(), 9)
