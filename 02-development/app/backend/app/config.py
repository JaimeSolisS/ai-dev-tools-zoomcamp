"""Runtime settings, read from environment variables."""

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Development mode returns magic-link tokens in the API response (no email is sent).
    dev_mode: bool = field(default_factory=lambda: _bool("ARCHBOARD_DEV", True))
    # Load demo users and sessions at startup.
    seed: bool = field(default_factory=lambda: _bool("ARCHBOARD_SEED", True))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.environ.get("ARCHBOARD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        )
    )
    magic_link_ttl_minutes: int = 15
    max_participants: int = 10
    # A participant counts as active for capacity checks if seen within this window.
    active_window_seconds: int = 30
