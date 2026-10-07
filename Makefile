.PHONY: help setup up down migrate migration-generate cli-scrape cli-export cli-status cli-stop cli-reset cli-worker api web web-build test check clean

executor ?= memory
broker_url ?= redis://localhost:6379/0

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python dependencies and prepare the local database
	@uv sync --frozen --extra web
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@docker compose up -d --wait db
	@$(MAKE) migrate
	@echo "Environment setup complete!"

up: ## Start the app (executor=memory|broker; broker adds Redis and worker)
	@SCRAPE_EXECUTOR=$(executor) docker compose $(if $(filter broker,$(executor)),--profile broker) up --build -d
	@echo "App: http://localhost:3000 | API docs: http://localhost:8000/docs"

down: ## Stop all docker containers
	@docker compose --profile broker down

api: ## Start FastAPI REST API server at http://127.0.0.1:8000
	@uv run --extra web job-scrapper api

web: frontend/node_modules/.package-lock.json ## Start React frontend development server at http://localhost:3000
	@npm --prefix frontend run dev

web-build: frontend/node_modules/.package-lock.json ## Build React frontend production bundle
	@npm --prefix frontend run build

frontend/node_modules/.package-lock.json: frontend/package.json frontend/package-lock.json
	@npm --prefix frontend ci

migrate: ## Apply database migrations and populate missing company seed records
	@uv run alembic upgrade head
	@uv run python -m job_scrapper.companies.bootstrap

migration-generate: ## Generate a new migration (usage: make migration-generate msg="your_message")
	@uv run alembic revision --autogenerate -m "$(msg)"

cli-scrape: ## Scrape sources (source=all days=7 separate=1 executor=memory|broker)
	@SCRAPE_EXECUTOR=$(executor) SCRAPE_BROKER_URL=$(broker_url) uv run --extra browser $(if $(filter broker,$(executor)),--extra broker) job-scrapper scrape --source $(or $(source),all) --days $(or $(days),7) $(if $(filter 1,$(separate)),--separate-runs)

cli-stop: ## Stop one scrape (run_id=...; required when several runs are active)
	@uv run job-scrapper stop $(if $(run_id),--run-id $(run_id))

cli-worker: ## Start the external Redis worker (broker_url=redis://localhost:6379/0)
	@SCRAPE_EXECUTOR=broker SCRAPE_BROKER_URL=$(broker_url) uv run --extra broker job-scrapper worker

cli-export: ## Export jobs (format=jsonl|parquet, days=7, out=data/jobs_dataset.<format>)
	@uv run $(if $(filter parquet,$(format)),--extra export) job-scrapper export --format $(or $(format),jsonl) --days $(or $(days),7) --output $(or $(out),data/jobs_dataset.$(or $(format),jsonl))

cli-status: ## Show current database status and job counts
	@uv run job-scrapper status

cli-reset: ## Delete all collected jobs, sightings, and scrape runs
	@uv run job-scrapper reset

test: ## Run unit tests
	@uv run pytest tests/

check: ## Run correctness lint and unit tests
	@uv run --frozen ruff check src tests
	@$(MAKE) test

clean: ## Clean build artifacts, Python cache and temporary files
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@rm -rf frontend/dist
