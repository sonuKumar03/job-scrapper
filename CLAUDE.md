# CLAUDE.md

Quick reference and developer commands for `job-scrapper`.

## Priority & Disposable Scraped Data

- The main goal is reliable, complete, and efficient scraping at scale (~10k jobs/day). Prioritize improving the scraping workflow and throughput.
- Existing scraped data is disposable. Agents may delete or reset this project's scraped jobs, sightings, scrape-run records, and generated dataset exports when required for development, fixes, or validation, without asking for additional confirmation.
- Backups, historical data recovery, and compatibility with old scraped records are not required. Scope resets to this project's scraped data and preserve unrelated databases, tables, files, and services.

---

### 1. Developer Commands (via Makefile)
```bash
# Setup environment (install deps, copy env, start Postgres, run migrations)
make setup

# Scrape jobs (default: all sources, last 90 days)
make scrape source=all days=90

# Export dataset for ML classification
make export days=90 out=data/jobs_dataset.jsonl

# View database status & counts
make status

# Run minimal tests
make test
```

### 2. Manual CLI & Dependency Commands

### 2. Database & Migrations
```bash
# Start local PostgreSQL 16 container
rtk docker compose up -d

# Stop PostgreSQL
rtk docker compose down

# Apply database migrations
rtk uv run alembic upgrade head

# Create a new migration revision
rtk uv run alembic revision --autogenerate -m "describe_change"
```

### 3. Scraping & Exporting
```bash
# Scrape from a specific board (e.g., Himalayas)
rtk uv run job-scrapper scrape --source himalayas --days 7

# Scrape all configured sources
rtk uv run job-scrapper scrape --source all --days 7

# Export scraped dataset to JSONL for ML model training
rtk uv run job-scrapper export --days 7 --format jsonl --output data/jobs_dataset.jsonl

# Inspect database stats
rtk uv run job-scrapper status
```

### 4. Testing (Minimal Policy)
```bash
# Run tests
rtk uv run pytest tests/
```

---

## 📐 Architecture & Conventions

1. **Decoupled Sinks**: Connectors must only interact with `JobSink` and yield `JobPosting` objects. Never import database models or engines inside `connectors/`.
2. **Dynamic Attributes**: Store ML classification tags inside `JobPosting.attributes` (`dict[str, Any]`), mapped to PostgreSQL `JSONB`.
3. **Anti-Bot & Rate Limits**:
   - Use `ResilientHttpClient` (`curl_cffi` impersonating `chrome120`).
   - Enforce 1–3s jitter and max 3 concurrent requests per domain.
4. **Command Execution**: Always prefix terminal commands with `rtk ` (e.g. `rtk uv run ...`).
