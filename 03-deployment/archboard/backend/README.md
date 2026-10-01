# Archboard backend

A FastAPI implementation of [`../openapi.yaml`](../openapi.yaml), the API that the frontend
in `../frontend` expects. Data is stored in a SQL database through SQLAlchemy: SQLite by
default, or Postgres, chosen with `DATABASE_URL`.

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8091   # http://localhost:8091  (Swagger UI at /docs)
uv run pytest                            # tests
uv run ruff check . && uv run ruff format --check .
```

### Database

The server connects to the database named by `DATABASE_URL`, a
[SQLAlchemy URL](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls):

```bash
# default: a SQLite file in the backend folder
DATABASE_URL=sqlite:///./archboard.db uv run uvicorn app.main:app --reload --port 8091

# another file
DATABASE_URL=sqlite:////absolute/path/to/archboard.db make run
```

Missing tables are created at startup. The demo data is loaded only into an empty database,
so your data survives restarts. `make reset-db` deletes the local SQLite file.

**Postgres.** The `psycopg` driver is a dependency. Point `DATABASE_URL` at an existing
database; the tables are created on first start:

```bash
docker run -d --name archboard-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=archboard -p 5432:5432 postgres:17
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/archboard make run
```

Tables use only portable column types, and all queries go through SQLAlchemy. Dialect-specific
setup lives in `app/db.py` (for SQLite: foreign keys and WAL mode). Schema changes are not
migrated yet: add a migration tool (Alembic) in place of the `create_all` at startup before
changing tables on a database that holds real data.

### Demo data

| Account             | Password      | Sessions                                         |
|---------------------|---------------|--------------------------------------------------|
| `ada@example.com`   | `password123` | ended example, live "Design a chat app", draft   |
| `grace@example.com` | `password123` | one draft                                        |

A candidate can join the live chat interview with the fixed demo link token
`demo-candidate-link-for-the-chat-app-interview` (`POST /v1/join/{token}`).
Anyone who signs up later through a magic link gets their own copy of the example session.

### Settings (environment variables)

| Variable                 | Default                                        | Meaning                                                  |
|--------------------------|------------------------------------------------|----------------------------------------------------------|
| `DATABASE_URL`           | `sqlite:///./archboard.db`                     | SQLAlchemy URL of the database                           |
| `ARCHBOARD_DEV`          | `true`                                         | Return magic-link tokens as `devToken` instead of emailing them |
| `ARCHBOARD_SEED`         | `true`                                         | Load the demo data into an empty database                |
| `ARCHBOARD_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`  | Allowed browser origins                                  |
| `ARCHBOARD_STATIC_DIR`   | (unset)                                        | Built frontend folder to serve at `/` (used by the Docker image) |

## Authentication

- **Interviewers** sign in with `POST /v1/auth/login` (email and password) or with a magic
  link (`POST /v1/auth/magic-link`, then `/verify`). Both return an `accessToken`, which is
  sent as `Authorization: Bearer <token>`.
- **Guests** join through `POST /v1/join/{token}` and receive a `credential`. It works for that
  one session only and is sent as `X-Guest-Credential`.
- **WebSocket** clients pass `?access_token=` or `?guest_credential=` in the URL.

Passwords are stored as salted scrypt hashes. Access tokens, guest credentials, magic-link
tokens and invitation tokens are 256-bit random values, and only their SHA-256 hashes are
stored. Every request is authorized on the server, and so is every WebSocket message.

## Layout

```
app/
  main.py          create_app(): wires the store, WebSocket hub, CORS, error handlers and routers
  config.py        settings from environment variables
  models.py        Pydantic request/response models (snake_case in Python, camelCase in JSON)
  db.py            engine from DATABASE_URL, per-dialect setup, portable UTC datetime type
  tables.py        SQLAlchemy ORM tables (follows the data model in _docs/spec.md §11)
  store.py         domain rules on top of the database (lifecycle, links, joins, permissions, canvas)
  auth.py          FastAPI dependencies: CurrentUser, OptionalUser, Principal (user or guest per session)
  security.py      scrypt password hashing and token hashing
  permissions.py   permission matrix (spec §9), mirrors frontend/src/services/permissions.ts
  canvas.py        canvas operation schema and last-writer-wins merge
  realtime.py      WebSocket hub: per-connection queues, fan-out, forced disconnects
  errors.py        ApiError with the spec's error codes, rendered as {code, message}
  seed.py          demo users and sessions
  routers/         one module per tag: auth, sessions, participants, guest_links, join, canvas, realtime
tests/             pytest suite, including test_contract.py, which checks the app against openapi.yaml
```

Each request gets one `Store`, which wraps one SQLAlchemy session and therefore one
transaction. The transaction commits before the response is sent and rolls back on errors.
WebSocket messages get a transaction each. Routes are plain `def` functions, so FastAPI runs
them in its threadpool and database calls never block the event loop.

Room events are buffered and sent through `realtime.Hub` only after the commit, so clients
never refetch data that isn't saved yet. The hub is thread-safe.

Canvas elements are stored one row each. Last-writer-wins is decided inside a single
conditional `UPDATE`, and duplicate operations are rejected by a unique constraint on the
operation log. Both stay correct when several writers hit the database at once.

## Tests

- `test_contract.py`: the app implements exactly the operations in `openapi.yaml`. It then
  exercises every HTTP operation and validates each response body, success and error alike,
  against the schemas in the spec. It also validates WebSocket messages against
  `ServerMessage`.
- `test_auth.py`, `test_security.py`: password login, tokens, logout, magic links, hashing.
- `test_sessions.py`, `test_links_and_join.py`, `test_canvas.py`: lifecycle, validation,
  ownership checks, link rules (revoke, expiry, max uses, capacity, rotation), permissions,
  snapshots and the merge rules.
- `test_realtime.py`: acks, fan-out, de-duplication, the editing lock, actor spoofing,
  observers, presence, room events and forced disconnects.
- `test_seed.py`: the demo accounts, the demo link, and a check that seeded canvases match the
  canvas schema.
- `test_database.py`: data survives a restart, seeding happens only once, `DATABASE_URL` is
  respected, SQLite settings, portable UTC datetimes, last-writer-wins and de-duplication in
  SQL, events only after commit, rollback on failure, and concurrent writers.

Every test runs against its own temporary SQLite file. To run the suite on Postgres, set
`TEST_DATABASE_URL` to a server the tests can create databases on (each test gets its own,
dropped afterwards), or use `make test-backend-postgres` from the repo root, which starts a
throwaway Postgres container:

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres uv run pytest
```

**Deployment tests.** `integration_tests/` checks the stack in `../docker-compose.yaml` from the
outside: it builds the image, starts the app and Postgres under its own project name on a free
port, and deletes them afterwards. They cover what unit tests can't: the image serves the
frontend (including share links opened directly), API paths still return JSON, data goes to
Postgres, a full share-link interview with WebSocket collaboration through the published port,
data surviving a recreated app container, and the app recovering when Postgres restarts. They
are not part of `uv run pytest`; run them with `make test-compose` (about a minute, needs Docker).
