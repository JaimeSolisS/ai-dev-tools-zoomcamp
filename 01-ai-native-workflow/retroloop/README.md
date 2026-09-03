# retroloop

Weekly team feedback and retrospective tool. See `_docs/plan.md` for scope,
`_docs/architecture.md` for design, `_docs/tasks.md` for build order.

## Quick start (Docker Compose)

Requires only Docker — no local Python or Postgres install.

```
cp .env.example .env   # edit SECRET_KEY before anything but local dev
docker compose up -d
docker compose run --rm web uv run manage.py migrate
```

The app is at http://localhost:8000/.

Run the test suite inside the container:

```
docker compose run --rm web uv run pytest
```

Services: `db` (Postgres 18), `web` (gunicorn), `worker` (placeholder — the
real task-queue worker lands in a later task). `web` and `worker` share a
`scratch` volume for the media pipeline; it holds nothing of value and can be
wiped at any time.

## Local (non-Docker) development

```
uv sync
uv run manage.py migrate
uv run manage.py runserver
```

Point `DATABASE_URL` in `.env` at a Postgres instance reachable from your
host (e.g. `localhost` instead of the Compose service name `db`).
