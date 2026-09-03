"""
Test settings module. Supplies safe defaults via os.environ.setdefault so
pytest can run without a local .env file, then defers to settings.py for
everything else.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault(
    "DATABASE_URL", "postgres://retroloop:retroloop@localhost:5432/retroloop_test"
)

from config.settings import *  # noqa: E402, F403
