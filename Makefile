# =============================================================================
# Orivanta AI — Makefile
# =============================================================================

.PHONY: help dev stop build test lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Docker ----------------------------------------------------------------

dev: ## Start all services (development)
	docker compose up --build

stop: ## Stop all services
	docker compose down

build: ## Build all containers
	docker compose build

logs: ## Tail all logs
	docker compose logs -f

# --- Frontend ---------------------------------------------------------------

frontend-dev: ## Run frontend dev server locally
	cd frontend && npm run dev

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

frontend-build: ## Build frontend for production
	cd frontend && npm run build

frontend-lint: ## Lint frontend code
	cd frontend && npm run lint

# --- Backend ----------------------------------------------------------------

backend-dev: ## Run backend dev server locally
	cd backend && uvicorn src.main:app --reload --port 8000

backend-install: ## Install backend dependencies
	cd backend && pip install -r requirements.txt

backend-test: ## Run backend tests
	cd backend && pytest -v

backend-lint: ## Lint backend code
	cd backend && ruff check src/

# --- Database ---------------------------------------------------------------

db-migrate: ## Run database migrations
	cd backend && alembic upgrade head

db-makemigration: ## Create a new migration
	cd backend && alembic revision --autogenerate -m "$(msg)"

db-downgrade: ## Downgrade last migration
	cd backend && alembic downgrade -1

# --- Utilities --------------------------------------------------------------

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
