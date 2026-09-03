# Chorely

A Django MVP for managing shared household chores. See `_docs/plan.md` for
the full product plan and `_docs/backlog.md` for the implementation backlog.

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

Then visit http://127.0.0.1:8000/ and log in with the superuser account you
created (the first admin login automatically gets its own household — see
Notes below). From there:

- **Calendar** (`/`) — the home screen, Month view by default. Toggle
  Month/Week, navigate periods, click a day's `+N more` to see all chores for
  that date, and click a chore to open its detail page.
- **New Chore** (`/chores/new/`) — admins can assign to any member(s) or
  leave unassigned; members can only create chores assigned to themselves.
  Due date must be today or later.
- **Chore detail** (`/chores/<id>/`) — shows full chore info; assignees get
  status-change buttons (Pending/In progress/Done, per the allowed
  transitions), unassigned chores show a **Claim** button to members, and
  admins get an **Edit** link (disabled once a chore is Done).
- **History** (`/history/`) — read-only chronological list of completed
  chores (title + completion date only).
- **Manage Members** (`/manage/members/`, admins only) — create members
  (username, password, display name) and remove them. Removing a member
  keeps their historical record but clears them from any unfinished chores.
- Django admin is still available at `/admin/` for direct data inspection.

## Running tests

```bash
# Run the whole suite
uv run python manage.py test

# Run one test module/class/method
uv run python manage.py test chores.tests.StatusTransitionTests
uv run python manage.py test chores.tests.StatusTransitionTests.test_admin_can_set_any_status_directly

# Verbose output (per-test pass/fail as it runs)
uv run python manage.py test -v 2
```

`chores/tests.py` covers, by scenario:

- **Status lifecycle** — legal member transitions (Pending↔In progress↔Done),
  illegal ones rejected, admin can set any status directly, only an assignee
  (any one of several) may change status, `CompletionHistory` is
  created/removed on Done/reopen.
- **Overdue** — past-due + not-Done is overdue; past-due-but-Done and
  future-due are not.
- **Claiming** — a member can claim an unassigned chore, cannot claim one
  that's already assigned, and admins cannot claim at all.
- **Edit locking** — Done chores can't be edited; unfinished ones can, and an
  admin can move an overdue chore to a future date.
- **View-level permissions** — members are blocked (403) from the edit view
  and both member-management screens; a member's chore is always forced to
  assignee=self regardless of what's posted; no delete route exists anywhere.
- **HTTP-level status/claim actions** — GET is rejected (POST-only), illegal
  or unauthorized attempts redirect with a flash message instead of
  crashing, and legal ones actually change the database.
- **Household isolation** — a chore, member, or calendar entry from one
  household is never visible (404 or absent from the page) to another
  household's users.
- **Calendar, day, and history views** — a chore renders on its due date,
  the `+N more` overflow link appears past the per-day cap, the day-detail
  page lists every chore for that date, and history is ordered
  most-recently-completed first and only ever shows title + completion date.
- **Member management** — duplicate usernames are rejected, a newly created
  member can actually log in, and removal deactivates the member while
  unassigning only their unfinished chores (Done chores keep their record).
- **`seed_categories` command** — creates the 9 fixed categories and is
  idempotent (running it twice doesn't duplicate rows).

Tests use `django.contrib.auth.hashers.MD5PasswordHasher` instead of the
default PBKDF2 hasher (see `config/settings.py`, gated on `'test' in
sys.argv`) — this is test-only and has no effect on real deployments; it
just avoids re-hashing passwords with a slow algorithm for every test user.

## Project layout

- `config/` — Django project settings, root URLs, WSGI/ASGI entrypoints.
- `chores/` — the app:
  - `models.py` — `Household`, `User`, `Category`, `Chore`, `ChoreAssignee`,
    `CompletionHistory`, plus the status-transition/claim/overdue logic.
  - `views.py`, `urls.py`, `forms.py` — calendar, chore CRUD, status/claim
    actions, completion history, and member management.
  - `templates/chores/` — server-rendered templates (no JS framework).
  - `signals.py` — bootstraps a `Household` for a user's first login (e.g.
    a freshly created superuser) so there's no separate setup step.
  - `management/commands/seed_categories.py` — seeds the fixed category list.
  - `tests.py` — see "Running tests" below for what's covered.
- `_docs/plan.md` — product/MVP plan.
- `_docs/backlog.md` — task backlog derived from the plan.

## Notes

- `AUTH_USER_MODEL` is set to `chores.User`, a custom user model extending
  Django's `AbstractUser` with `display_name`, `role` (admin/member), and a
  `household` foreign key.
- `db.sqlite3` and `.venv/` are gitignored; each environment runs its own
  `migrate` to build the database locally.
- Dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`). Add new
  packages with `uv add <package>` rather than editing `pyproject.toml` by
  hand, so the lockfile stays in sync.
- The plan describes chore/day details opening in a "popup". This MVP
  implements them as plain server-rendered pages (no JS) rather than modal
  dialogs — same information, simpler implementation.
