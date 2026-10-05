.PHONY: help setup up down migrate scrape export parquet status reset test clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and prepare local environment
	@rtk uv sync --extra dev
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@rtk docker compose up -d
	@sleep 2
	@rtk uv run alembic upgrade head
	@echo "Environment setup complete!"

up: ## Start PostgreSQL container
	@rtk docker compose up -d

down: ## Stop PostgreSQL container
	@rtk docker compose down

migrate: ## Apply database migrations
	@rtk uv run alembic upgrade head

migration-generate: ## Generate a new migration (usage: make migration-generate msg="your_message")
	@rtk uv run alembic revision --autogenerate -m "$(msg)"

scrape: ## Scrape all sources from the last 7 days
	@rtk uv run job-scrapper scrape --source $(or $(source),all) --days $(or $(days),7)

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

clean: ## Clean Python cache and temporary files
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
