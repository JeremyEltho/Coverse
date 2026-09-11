# Coverse. `make dev` runs both halves; everything else is a single task.

.PHONY: help setup dev backend frontend test lint check clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend and frontend dependencies
	cd server && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd web && npm install

dev: ## Run backend and frontend together
	@$(MAKE) -j2 backend frontend

backend: ## Run the API and websocket server on :8000
	cd server && .venv/bin/python -m uvicorn coverse.main:app --reload --port 8000

frontend: ## Run the Vite dev server on :5173
	cd web && npm run dev

test: ## Run backend tests and the frontend typecheck
	cd server && .venv/bin/python -m pytest -q
	cd web && npx tsc --noEmit

lint: ## Lint and type-check the backend
	cd server && .venv/bin/ruff check coverse tests
	cd server && .venv/bin/ruff format --check coverse tests
	cd server && .venv/bin/mypy coverse

check: ## End-to-end checks against running servers (make dev first)
	cd web && node scripts/room-check.mjs
	cd web && node scripts/e2e-check.mjs

clean:
	rm -rf web/dist server/.pytest_cache server/.ruff_cache server/.mypy_cache
