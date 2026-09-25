# Archboard backend

A FastAPI implementation of [`../openapi.yaml`](../openapi.yaml), the API that the frontend
in `../frontend` expects. All state is kept in memory and loaded with demo data at startup, so
a restart resets everything.

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8091   # http://localhost:8091  (Swagger UI at /docs)
uv run pytest                            # tests
uv run ruff check . && uv run ruff format --check .
```

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
| `ARCHBOARD_DEV`          | `true`                                         | Return magic-link tokens as `devToken` instead of emailing them |
| `ARCHBOARD_SEED`         | `true`                                         | Load the demo data                                       |
| `ARCHBOARD_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`  | Allowed browser origins                                  |

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
  store.py         in-memory store and all domain rules (lifecycle, links, joins, permissions, canvas)
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

The store runs entirely on the event loop, and every route and dependency is `async`, so it
needs no locking. The store emits room events through an `EventSink` interface, which
`realtime.Hub` implements, so domain code never touches sockets.

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
