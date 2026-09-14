# Balancio

Split expenses. Settle balances.

Balancio is a general-purpose shared expense splitter for friends, households, couples, trips, and other small groups. It supports users and groups, expenses with multiple payers and equal splits, group and global balance tracking, simplified settlement suggestions, settlements, and refunds.

See [`_docs/specs.md`](_docs/specs.md) for the full product and implementation specification, and [`openapi.yaml`](openapi.yaml) for the REST API contract.

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for Python dependency and environment management
- Node.js 20+ and npm

## Backend setup

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

The API is served under `/api/v1`. FastAPI's automatically generated OpenAPI/Swagger docs (available at `/docs` while the server is running) are sufficient for API exploration.

### Environment variables

Copy `backend/.env.example` to `backend/.env` and adjust as needed:

```env
APP_NAME=Balancio
APP_CURRENCY=MXN
JWT_SECRET=change-me
JWT_EXPIRATION_HOURS=8
DATA_FILE=./data/balancio.json
ENVIRONMENT=development
```

Data persists to a local JSON file (`backend/data/balancio.json`) across restarts. No database server is required for the MVP.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

## Running tests

```bash
# Backend unit, API/integration tests
cd backend
uv run pytest

# Frontend component tests
cd frontend
npm test

# End-to-end tests
cd frontend
npm run test:e2e
```

No Docker or deployment configuration is required to run Balancio locally.
