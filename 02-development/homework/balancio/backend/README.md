# Balancio backend

FastAPI backend for Balancio. See [`../openapi.yaml`](../openapi.yaml) for the
full API contract and [`../_docs/specs.md`](../_docs/specs.md) for the product
spec.

## Stack

- FastAPI + Pydantic v2
- JWT auth (PyJWT), PBKDF2 password hashing (stdlib `hashlib`, no native deps)
- SQLAlchemy + SQLite (`data/balancio.db`) behind a repository abstraction
  (`app/repositories/`), so the database engine can change (via
  `DATABASE_URL`, e.g. to Postgres or MySQL) without touching route or
  service code
- `uv` for dependency and environment management

## Setup

```bash
uv sync
cp .env.example .env  # optional, defaults work out of the box
```

## Run

```bash
uv run fastapi dev app/main.py
```

The API is served under `/api/v1`. Interactive docs: `http://localhost:8000/docs`.

## Test

```bash
uv run pytest              # whole suite
uv run pytest tests/test_balance_calculator.py   # one file
```

Tests never touch the real `data/balancio.db` - each test gets a fresh,
isolated in-memory SQLite database (see `tests/conftest.py`).

## Lint & type-check

```bash
uv run ruff check .
uv run mypy app/
```

## Project layout

```text
app/
├── main.py            # FastAPI app factory, exception handlers, routing
├── config.py          # Settings (env vars)
├── security.py        # Password hashing + JWT
├── dependencies.py     # Auth/repo dependencies for routes
├── errors.py          # AppError -> friendly {"message": ...} responses
├── models/domain.py   # Persisted entity models (Pydantic)
├── schemas/           # Request/response DTOs per domain area
├── repositories/       # Repository abstraction + SQLAlchemy-backed implementation
├── services/
│   ├── balance_calculator.py  # The balance engine (pure functions)
│   └── identity.py    # ID generation
└── routes/            # One router per domain area
```
