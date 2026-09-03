from django.contrib.auth.models import AbstractUser
from django.db import models


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

    def __str__(self):
        return self.title


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
