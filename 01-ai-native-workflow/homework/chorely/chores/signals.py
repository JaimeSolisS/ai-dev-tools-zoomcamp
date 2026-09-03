from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Household, User


@receiver(user_logged_in)
def ensure_household(sender, user, request, **kwargs):
    """Bootstrap a household for a user who doesn't have one yet (e.g. a
    freshly created superuser via createsuperuser)."""
    if user.household_id is not None:
        return
    household = Household.objects.create()
    user.household = household
    if user.is_superuser:
        user.role = User.Role.ADMIN
    user.save(update_fields=["household", "role"])
