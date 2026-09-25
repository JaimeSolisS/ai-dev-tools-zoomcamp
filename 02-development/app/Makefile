# Archboard: run `make help` to list targets.

FRONTEND := frontend
BACKEND  := backend
BACKEND_PORT  ?= 8091
FRONTEND_PORT ?= 5173

.DEFAULT_GOAL := help
.PHONY: help install install-frontend install-backend run dev frontend backend \
        test test-frontend test-backend test-integration lint build clean reset-db

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: install-frontend install-backend ## Install all dependencies

install-frontend: ## Install frontend dependencies (npm)
	cd $(FRONTEND) && npm install

install-backend: ## Install backend dependencies (uv)
	cd $(BACKEND) && uv sync

run: backend ## Run the backend (same as `make backend`)

dev: ## Run backend and frontend together (Ctrl+C stops both)
	@$(MAKE) --no-print-directory -j2 backend frontend

frontend: ## Run the frontend dev server (http://localhost:5173)
	cd $(FRONTEND) && npm run dev -- --port $(FRONTEND_PORT)

backend: ## Run the backend with auto-reload (http://localhost:8091/docs); DATABASE_URL picks the database
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port $(BACKEND_PORT)

test: test-backend test-frontend ## Run all tests

test-frontend: ## Run frontend tests (Vitest)
	cd $(FRONTEND) && npm test

test-backend: ## Run backend tests (pytest)
	cd $(BACKEND) && uv run pytest

INTEGRATION_PORT ?= 8092

test-integration: ## Run the frontend's HTTP client against a freshly started backend
	@cd $(BACKEND) && uv sync -q
	@tmp=$$(mktemp -d); \
	DATABASE_URL=sqlite:///$$tmp/integration.db $(BACKEND)/.venv/bin/uvicorn --app-dir $(BACKEND) app.main:app \
		--port $(INTEGRATION_PORT) > /dev/null 2>&1 & pid=$$!; \
	trap "kill $$pid 2>/dev/null; rm -rf $$tmp" EXIT; \
	for i in $$(seq 1 50); do curl -sf http://localhost:$(INTEGRATION_PORT)/docs > /dev/null && break; sleep 0.2; done; \
	cd $(FRONTEND) && ARCHBOARD_API_URL=http://localhost:$(INTEGRATION_PORT) npx vitest run src/services/http/httpBackend.integration.test.ts

lint: ## Type-check the frontend, lint and format-check the backend
	cd $(FRONTEND) && npm run typecheck
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

build: ## Build the frontend for production
	cd $(FRONTEND) && npm run build

reset-db: ## Delete the local SQLite database (the demo data is re-seeded on next start)
	rm -f $(BACKEND)/archboard.db $(BACKEND)/archboard.db-shm $(BACKEND)/archboard.db-wal

clean: ## Remove build output and caches
	rm -rf $(FRONTEND)/dist $(FRONTEND)/tsconfig.tsbuildinfo
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
