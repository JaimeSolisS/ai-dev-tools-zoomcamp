Commands

- `cd backend && uv sync` - install backend dependencies
- `cd backend && uv run fastapi dev app/main.py` - run the API locally
- `cd backend && uv run pytest` - the whole backend test suite
- `cd backend && uv run pytest tests/test_balances.py` - one test file
- `cd backend && uv run ruff check .` - lint
- `cd backend && uv run ruff format .` - format
- `cd backend && uv run mypy app/` - type-check
- `cd frontend && npm install` - install frontend dependencies
- `cd frontend && npm run dev` - run the frontend locally
- `cd frontend && npm test` - frontend component tests
- `cd frontend && npm run test:e2e` - end-to-end browser tests
- `cd frontend && npm run lint` - lint

Rules

- Backend dependencies are added in `backend/pyproject.toml`. Do not add one
  without asking.
- Frontend dependencies are added in `frontend/package.json`. Do not add one
  without asking. Do not introduce Redux, Zustand, or TanStack Query for the
  MVP.
- Do not add Docker or CI configuration.
- Persistence is SQLAlchemy + SQLite (`backend/data/balancio.db`) via the
  repository abstraction (`backend/app/repositories/`). The database engine
  is configured through `DATABASE_URL`; do not hardcode a specific dialect
  outside of `app/repositories/database.py`.
- Business logic (especially balance calculation) must not depend on
  SQLAlchemy or ORM-specific behavior - it must only see plain domain
  (Pydantic) models via the repository interfaces, so persistence can
  change again later without touching business logic.
- All monetary calculations must use decimal arithmetic, never binary
  floating point, and must always reconcile to the cent.
- See `_docs/specs.md` for the full product and implementation specification.
