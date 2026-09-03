from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Category, Chore, ChoreAssignee, CompletionHistory, Household, User


@admin.register(User)
class ChorelyUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Household", {"fields": ("display_name", "role", "household")}),
    )
    list_display = ("username", "display_name", "role", "household", "is_active")


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_system")


class ChoreAssigneeInline(admin.TabularInline):
    model = ChoreAssignee
    extra = 0


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ("title", "household", "category", "status", "due_date")
    list_filter = ("status", "category", "household")
    inlines = [ChoreAssigneeInline]


@admin.register(CompletionHistory)
class CompletionHistoryAdmin(admin.ModelAdmin):
    list_display = ("chore", "completed_at")
