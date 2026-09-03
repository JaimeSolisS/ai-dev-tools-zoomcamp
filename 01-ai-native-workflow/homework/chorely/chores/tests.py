from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
