from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class Household(models.Model):
    """A single household. Users belong to exactly one in the MVP.

    Kept as its own model (rather than baked into User) so multiple
    households per user can be supported later without a schema rewrite.
    """

    name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or f"Household {self.pk}"


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    display_name = models.CharField(max_length=100)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    household = models.ForeignKey(
        Household,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )

    def __str__(self):
        return self.display_name or self.username

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN


class Category(models.Model):
    """Chore category. Fixed/system categories are seeded; the model
    allows custom categories to be added later."""

    name = models.CharField(max_length=50, unique=True)
    is_system = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Chore(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="chores"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="chores"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    assignees = models.ManyToManyField(
        User, through="ChoreAssignee", related_name="assigned_chores", blank=True
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_chores"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Transitions a member may make themselves, keyed by current status.
    MEMBER_TRANSITIONS = {
        Status.PENDING: {Status.IN_PROGRESS, Status.DONE},
        Status.IN_PROGRESS: {Status.DONE},
        Status.DONE: {Status.PENDING, Status.IN_PROGRESS},
    }

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return self.due_date < timezone.localdate() and self.status != self.Status.DONE

    @property
    def is_unassigned(self):
        return not self.assignees.exists()

    def is_locked(self):
        """Done chores are locked and cannot be edited."""
        return self.status == self.Status.DONE

    def can_be_edited_by_admin(self):
        return not self.is_locked()

    def can_be_claimed_by(self, user):
        return self.is_unassigned and not user.is_admin

    def claim(self, user):
        if not self.can_be_claimed_by(user):
            raise PermissionDenied("This chore cannot be claimed.")
        ChoreAssignee.objects.get_or_create(chore=self, user=user)

    def transition_status(self, user, new_status):
        """Apply a status change, enforcing role-based rules and keeping
        CompletionHistory in sync."""
        if new_status not in self.Status.values:
            raise ValueError(f"Unknown status: {new_status}")

        if user.is_admin:
            pass  # admins may set any status directly
        else:
            if not self.assignees.filter(pk=user.pk).exists():
                raise PermissionDenied("Only an assignee may change this chore's status.")
            allowed = self.MEMBER_TRANSITIONS.get(self.status, set())
            if new_status not in allowed:
                raise PermissionDenied(
                    f"Members cannot move a chore from {self.status} to {new_status}."
                )

        was_done = self.status == self.Status.DONE
        now_done = new_status == self.Status.DONE

        self.status = new_status
        if now_done and not was_done:
            self.completed_at = timezone.now()
            CompletionHistory.objects.update_or_create(
                chore=self, defaults={"completed_at": self.completed_at}
            )
        elif was_done and not now_done:
            self.completed_at = None
            CompletionHistory.objects.filter(chore=self).delete()

        self.save(update_fields=["status", "completed_at", "updated_at"])


class ChoreAssignee(models.Model):
    chore = models.ForeignKey(Chore, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("chore", "user")

    def __str__(self):
        return f"{self.user} -> {self.chore}"


class CompletionHistory(models.Model):
    """One active record per completed chore. Deleted when a Done chore
    is reopened, per the MVP's minimal-history rule."""

    chore = models.OneToOneField(
        Chore, on_delete=models.CASCADE, related_name="completion_record"
    )
    completed_at = models.DateTimeField()

    def __str__(self):
        return f"{self.chore.title} completed {self.completed_at:%Y-%m-%d}"
