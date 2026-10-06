.PHONY: help setup up down migrate migration-generate scrape export parquet status stop reset api web web-build test clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and prepare local environment
	@rtk uv sync --extra dev --extra web
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@rtk npm --prefix frontend install
	@rtk docker compose up -d db
	@sleep 2
	@rtk uv run alembic upgrade head
	@echo "Environment setup complete!"

up: ## Start all services in Docker Compose (db, api, web)
	@rtk docker compose up --build -d
	@echo "\n\033[32m✔ All services are running!\033[0m"
	@echo "  \033[36mReact Web App:\033[0m   http://localhost:3000"
	@echo "  \033[36mFastAPI Docs:\033[0m    http://localhost:8000/docs"
	@echo "  \033[36mPostgreSQL DB:\033[0m   localhost:5432\n"

down: ## Stop all docker containers
	@rtk docker compose down

api: ## Start FastAPI REST API server at http://127.0.0.1:8000
	@rtk uv run --extra web job-scrapper api

web: ## Start React frontend development server at http://localhost:5173
	@rtk npm --prefix frontend run dev

web-build: ## Build React frontend production bundle
	@rtk npm --prefix frontend run build

migrate: ## Apply database migrations
	@rtk uv run alembic upgrade head

migration-generate: ## Generate a new migration (usage: make migration-generate msg="your_message")
	@rtk uv run alembic revision --autogenerate -m "$(msg)"

scrape: ## Scrape all sources from the last 7 days
	@rtk uv run --extra browser job-scrapper scrape --source $(or $(source),all) --days $(or $(days),7)

stop: ## Gracefully stop the active CLI or web scrape after its current batch
	@rtk uv run job-scrapper stop

export: ## Export recent jobs to JSONL
	@rtk uv run job-scrapper export --days $(or $(days),7) --output $(or $(out),data/jobs_dataset.jsonl)

parquet: ## Export recent jobs to Parquet
	@rtk uv run --extra export job-scrapper export --format parquet

status: ## Show current database status and job counts
	@rtk uv run job-scrapper status

reset: ## Delete all collected jobs, sightings, and scrape runs
	@rtk uv run job-scrapper reset

test: ## Run unit tests
	@rtk uv run pytest tests/

clean: ## Clean build artifacts, Python cache and temporary files
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@rm -rf frontend/dist
