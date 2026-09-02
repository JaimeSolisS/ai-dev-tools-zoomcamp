"""
Test environment. Production settings (config/settings.py) stay strict and
require every variable to be set explicitly — this module supplies values so
the suite runs without a .env file.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("ALLOWED_HOSTS", "testserver")
os.environ.setdefault(
    "DATABASE_URL", "postgres://retroloop:retroloop@localhost:5432/retroloop_test"
)

from .settings import *  # noqa: E402, F403
