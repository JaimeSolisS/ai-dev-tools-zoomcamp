from django.core.management.base import BaseCommand

from chores.models import Category

CATEGORIES = [
    "Cleaning",
    "Kitchen",
    "Laundry",
    "Bathroom",
    "Bedroom",
    "Shopping",
    "Trash",
    "Pet Care",
    "Other",
]


class Command(BaseCommand):
    help = "Seed the fixed set of system chore categories."

    def handle(self, *args, **options):
        created = 0
        for name in CATEGORIES:
            _, was_created = Category.objects.get_or_create(
                name=name, defaults={"is_system": True}
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded categories: {created} created, "
                f"{len(CATEGORIES) - created} already existed."
            )
        )
