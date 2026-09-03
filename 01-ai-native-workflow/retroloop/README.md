# retroloop

Weekly Team Feedback Tool. See `_docs/plan.md` for scope, `_docs/architecture.md`
for design, `AGENTS.md` for how to work in this repo.

## Docker Compose quick start

Requires only Docker; no local Python or Postgres install needed.

1. Copy the environment file:

   ```sh
   cp .env.example .env
   ```

2. Edit `.env` and change the `DATABASE_URL` host from `localhost` to `db`,
   since Django runs inside the `web`/`worker` containers and reaches
   Postgres over the Compose network by service name, not `localhost`:

   ```
   DATABASE_URL=postgres://retroloop:retroloop@db:5432/retroloop
   ```

   Also set a real `SECRET_KEY`. Leave `POSTGRES_USER`, `POSTGRES_PASSWORD`,
   and `POSTGRES_DB` as-is (or change them together with the credentials
   embedded in `DATABASE_URL` — they must always match).

3. Build and start the stack:

   ```sh
   docker compose up -d --build
   ```

   This starts three services:
   - `db` — Postgres 18, data persisted in the `db-data` named volume
   - `web` — gunicorn serving the Django app on `http://localhost:8000`
   - `worker` — a placeholder container (the real `django-tasks-db` worker
     command lands in a later task)

   `web` and `worker` wait for `db`'s healthcheck (`pg_isready`) before
   starting, not just for the container to launch.

4. Run migrations:

   ```sh
   docker compose run web uv run manage.py migrate
   ```

5. Run the test suite inside the container:

   ```sh
   docker compose run web uv run pytest
   ```

6. Visit `http://localhost:8000` — you should get a 200 response.

### Bare metal vs. Compose: `DATABASE_URL`

`.env.example` ships `DATABASE_URL` with host `localhost`, which is correct
when running `uv run manage.py runserver` directly on your machine against a
locally installed Postgres. Under Docker Compose, Django runs inside a
container and must resolve Postgres by its Compose service name (`db`)
instead — `localhost` inside the `web`/`worker` containers refers to the
container itself, not the `db` container. Swap the host as shown in step 2
above when using Compose; swap it back to `localhost` for bare-metal runs.

### Data persistence

Postgres data lives in the named volume `db-data` and survives a plain
`docker compose down`. Only `docker compose down -v` (or deleting the volume
directly) destroys it. The `scratch` volume, shared between `web` and
`worker` for the media pipeline, holds nothing of value and can be wiped at
any time.

### Non-root user and the scratch volume

The image runs application code as a non-root `app` user. A freshly created
named volume is mounted root-owned by the Docker daemon regardless of the
image's `USER`, so `entrypoint.sh` runs as root at container start, `chown`s
the scratch mount point to `app`, and then drops privileges via `gosu`
before running the real command (gunicorn, or the worker placeholder).

## Bare-metal quick start

```sh
uv sync
cp .env.example .env   # DATABASE_URL host stays `localhost`
uv run manage.py migrate
uv run manage.py runserver
```

## Commands

- `uv sync` - install dependencies
- `uv run manage.py runserver` - dev server
- `uv run manage.py migrate` - apply migrations
- `uv run pytest` - the whole suite
- `uv run ruff check . && uv run ruff format --check .` - lint and format
