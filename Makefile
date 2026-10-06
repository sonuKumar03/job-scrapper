.PHONY: help setup up down migrate migration-generate cli-scrape cli-export cli-status cli-stop cli-reset api web web-build test clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python dependencies and prepare the local database
	@rtk uv sync --extra dev --extra web
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@rtk docker compose up -d --wait db
	@$(MAKE) migrate
	@echo "Environment setup complete!"

up: ## Start all services in Docker Compose (db, api, web)
	@rtk docker compose up --build -d
	@echo "App: http://localhost:3000 | API docs: http://localhost:8000/docs"

down: ## Stop all docker containers
	@rtk docker compose down

api: ## Start FastAPI REST API server at http://127.0.0.1:8000
	@rtk uv run --extra web job-scrapper api

web: frontend/node_modules/.package-lock.json ## Start React frontend development server at http://localhost:3000
	@rtk npm --prefix frontend run dev

web-build: frontend/node_modules/.package-lock.json ## Build React frontend production bundle
	@rtk npm --prefix frontend run build

frontend/node_modules/.package-lock.json: frontend/package.json frontend/package-lock.json
	@rtk npm --prefix frontend install

migrate: ## Apply database migrations
	@rtk uv run alembic upgrade head

migration-generate: ## Generate a new migration (usage: make migration-generate msg="your_message")
	@rtk uv run alembic revision --autogenerate -m "$(msg)"

cli-scrape: ## Scrape all sources from the last 7 days
	@rtk uv run --extra browser job-scrapper scrape --source $(or $(source),all) --days $(or $(days),7)

cli-stop: ## Gracefully stop the active CLI or web scrape after its current batch
	@rtk uv run job-scrapper stop

cli-export: ## Export jobs (format=jsonl|parquet, days=7, out=data/jobs_dataset.<format>)
	@rtk uv run $(if $(filter parquet,$(format)),--extra export) job-scrapper export --format $(or $(format),jsonl) --days $(or $(days),7) --output $(or $(out),data/jobs_dataset.$(or $(format),jsonl))

cli-status: ## Show current database status and job counts
	@rtk uv run job-scrapper status

cli-reset: ## Delete all collected jobs, sightings, and scrape runs
	@rtk uv run job-scrapper reset

test: ## Run unit tests
	@rtk uv run pytest tests/

clean: ## Clean build artifacts, Python cache and temporary files
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@rm -rf frontend/dist
