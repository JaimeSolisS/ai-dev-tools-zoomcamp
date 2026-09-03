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
npm install
npm run build           # one-off build of CSS/JS, see "Frontend assets" below
uv run manage.py runserver
```

## Commands

- `uv sync` - install dependencies
- `uv run manage.py runserver` - dev server
- `uv run manage.py migrate` - apply migrations
- `uv run pytest` - the whole suite
- `uv run ruff check . && uv run ruff format --check .` - lint and format
- `npm install` - install frontend build tooling (Tailwind CLI, vendored
  HTMX/Alpine)
- `npm run watch:css` - rebuild Tailwind CSS on every save, for local dev
- `npm run build` - one-off production build: compiled+minified CSS plus
  vendored HTMX/Alpine JS copied into `static/`
- `uv run manage.py collectstatic` - gather `static/` into `STATIC_ROOT`
  with cache-busted (hashed) filenames, for deploy

## Frontend assets (Tailwind / HTMX / Alpine)

Tailwind 4 is configured CSS-first — there is no `tailwind.config.js`.
`static_src/css/input.css` holds `@import "tailwindcss";`, an `@source`
directive scoping content-scanning to `templates/**/*.html`, and an empty
`@theme` block reserved for design tokens (`_docs/design-system.md` doesn't
exist yet — tracked separately in issue #29, not improvised here).

`static/` is the build **output** directory (gitignored, not committed) and
is what `STATICFILES_DIRS` points at:

- `static/css/app.css` — compiled, minified Tailwind CSS, built by the
  Tailwind CLI (`@tailwindcss/cli`) from `static_src/css/input.css`.
- `static/js/htmx.min.js` and `static/js/alpine.min.js` — HTMX 2.0.10 and
  Alpine 3.15.12, installed via npm and copied out of `node_modules` by
  `static_src/copy-vendor.js` (`npm run build:js`). They're served as local
  static files via `django.contrib.staticfiles`, never as CDN `<script
  src="https://...">` tags.

Local dev: run `npm run watch:css` in a separate terminal alongside
`uv run manage.py runserver` so CSS rebuilds on save. JS vendor files rarely
change, so `npm run build:js` is a one-off (re-run it after bumping the
htmx.org/alpinejs versions in `package.json`).

Production / deploy: run `npm ci && npm run build` before
`uv run manage.py collectstatic --noinput`. Nothing under `static/` or
`node_modules/` is committed to the repo, so both steps must run on every
fresh checkout/build — there are no pre-built assets checked in. `STATIC_ROOT`
uses Django's `ManifestStaticFilesStorage`, so every collected file gets a
content-hashed name (e.g. `app.<hash>.css`) and a redeploy can't serve a
stale cached asset to a returning browser.

## Accounts, login, and passwords

Signup (`/accounts/signup/`), login (`/accounts/login/`), and logout
(`/accounts/logout/`, POST-only) use the stock
`django.contrib.auth.models.User` model — no custom `AUTH_USER_MODEL`, no
profile table. A user's display name lives in `User.first_name`.

**There is no email address anywhere in this app, and no self-serve
password reset.** No mail backend is configured (per `AGENTS.md`), so
`password_reset/` and every other reset-flow URL normally bundled in
`django.contrib.auth.urls` are not wired — only login and logout are. If a
user forgets their password, an admin resets it from the command line:

```sh
uv run manage.py changepassword <username>
```

(or `docker compose run web uv run manage.py changepassword <username>`
under Compose). That's the only password-reset path.

### Flash messages and HTMX

`templates/base.html` renders Django's `messages` framework once, in the
page chrome, on every full page load. HTMX partial views (see the
`htmx-demo` endpoint) return only their fragment and never re-render
`base.html`, so a message queued with `messages.success(...)` (or similar)
during an HTMX request is **not** shown inside that same partial swap — it
stays in the session and appears in the flash region on the user's next
full page load/navigation. This decision (and the alternative a partial
view has if it needs immediate feedback) is documented as a code comment
next to the message block in `base.html`.
