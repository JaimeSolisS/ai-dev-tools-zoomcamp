# Chorely

A Django MVP for managing shared household chores. See `_docs/plan.md` for
the full product plan and `backlog.md` for the implementation backlog.

## Requirements

- [uv](https://docs.astral.sh/uv/) (manages the Python version and virtual
  environment for you — no separate Python install required)

## Setup

```bash
# Install dependencies (creates .venv/ and installs the pinned Python
# version automatically on first run)
uv sync

# Apply migrations
uv run python manage.py migrate

# Seed the fixed chore categories (Cleaning, Kitchen, Laundry, ...)
uv run python manage.py seed_categories

# Create an admin/superuser account
uv run python manage.py createsuperuser
```

## Running the app

```bash
uv run python manage.py runserver
```

Then visit http://127.0.0.1:8000/admin/ to log in and manage data via the
Django admin (the app's own UI is not built yet — see `backlog.md`).

## Project layout

- `config/` — Django project settings, root URLs, WSGI/ASGI entrypoints.
- `chores/` — the app: models (`Household`, `User`, `Category`, `Chore`,
  `ChoreAssignee`, `CompletionHistory`), admin registrations, and the
  `seed_categories` management command.
- `_docs/plan.md` — product/MVP plan.
- `backlog.md` — task backlog derived from the plan.

## Notes

- `AUTH_USER_MODEL` is set to `chores.User`, a custom user model extending
  Django's `AbstractUser` with `display_name`, `role` (admin/member), and a
  `household` foreign key.
- `db.sqlite3` and `.venv/` are gitignored; each environment runs its own
  `migrate` to build the database locally.
- Dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`). Add new
  packages with `uv add <package>` rather than editing `pyproject.toml` by
  hand, so the lockfile stays in sync.
