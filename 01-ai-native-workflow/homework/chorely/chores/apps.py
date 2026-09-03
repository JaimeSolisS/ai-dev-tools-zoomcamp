from django.apps import AppConfig


class ChoresConfig(AppConfig):
    name = 'chores'

    def ready(self):
        from . import signals  # noqa: F401
