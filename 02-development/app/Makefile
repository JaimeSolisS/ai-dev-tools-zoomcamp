# Archboard: run `make help` to list targets.

FRONTEND := frontend
BACKEND  := backend
BACKEND_PORT  ?= 8000
FRONTEND_PORT ?= 5173

.DEFAULT_GOAL := help
.PHONY: help install install-frontend install-backend dev frontend backend \
        test test-frontend test-backend lint build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: install-frontend install-backend ## Install all dependencies

install-frontend: ## Install frontend dependencies (npm)
	cd $(FRONTEND) && npm install

install-backend: ## Install backend dependencies (uv)
	cd $(BACKEND) && uv sync

dev: ## Run backend and frontend together (Ctrl+C stops both)
	@$(MAKE) --no-print-directory -j2 backend frontend

frontend: ## Run the frontend dev server (http://localhost:5173)
	cd $(FRONTEND) && npm run dev -- --port $(FRONTEND_PORT)

backend: ## Run the backend with auto-reload (http://localhost:8000/docs)
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port $(BACKEND_PORT)

test: test-backend test-frontend ## Run all tests

test-frontend: ## Run frontend tests (Vitest)
	cd $(FRONTEND) && npm test

test-backend: ## Run backend tests (pytest)
	cd $(BACKEND) && uv run pytest

lint: ## Type-check the frontend, lint and format-check the backend
	cd $(FRONTEND) && npm run typecheck
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

build: ## Build the frontend for production
	cd $(FRONTEND) && npm run build

clean: ## Remove build output and caches
	rm -rf $(FRONTEND)/dist $(FRONTEND)/tsconfig.tsbuildinfo
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
