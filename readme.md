# Job Scrapper

A high-volume, anti-bot resilient job scraping engine designed to collect recent job postings (<= 7 days) across popular job boards and export clean, structured datasets for training custom machine learning classification models.

---

## Key Features

- **Decoupled Architecture (Ports & Adapters)**:
  - **Connectors**: Independent, pluggable scrapers for each job board implementing `BaseConnector`.
  - **Storage Sinks**: Persistence is decoupled from scraping via the `JobSink` protocol (PostgreSQL, SQLite, or flat JSONL/Parquet files).
- **Anti-Bot Bypass**:
  - Uses `curl_cffi` to impersonate real browser TLS fingerprints (Chrome 120 / JA3/JA4) for fast scraping without getting blocked by Cloudflare/Akamai.
  - Headless browser fallback via `playwright` with stealth for dynamic JavaScript challenges.
- **Strict Recency Filtering**:
  - Automatically filters and normalizes publication dates into UTC, dropping postings older than a configurable cutoff (default: 7 days).
- **Extensible Classification Schema**:
  - Core canonical fields (`title`, `company_name`, `description_text`, `posted_at`) paired with a flexible `attributes` JSON payload (`seniority`, `work_arrangement`, `location`, `salary_min`, `salary_max`, `experience_years_min`, `experience_years_max`, `tech_stack`).
  - Add or modify classification labels without database migrations.
- **High-Performance ML Dataset Export**:
  - Export directly from PostgreSQL to `.jsonl` or `.parquet` formatted for tokenization and model fine-tuning.

---

## Architecture

```
                       ┌─────────────────────────┐
                       │  Target Job Boards       │
                       │  (Himalayas, Jobicy, etc│
                       └────────────┬────────────┘
                                    │
                        curl_cffi / Playwright
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │  Pluggable Connectors   │
                       │  (implements Base)      │
                       └────────────┬────────────┘
                                    │
                         Raw Payloads / HTML
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │  Normalization Pipeline │
                       │  • HTML Cleaner         │
                       │  • UTC Date Filter (<7d)│
                       │  • SHA-256 Content Dedup│
                       └────────────┬────────────┘
                                    │
                         Canonical JobPosting
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │  JobSink Protocol       │
                       └──────┬───────────┬──────┘
                              │           │
            ┌─────────────────▼───┐   ┌───▼─────────────────┐
            │ PostgresJobSink     │   │ FileJobSink         │
            │ (SQLAlchemy 2.0)    │   │ (JSONL / Parquet)   │
            └─────────────────────┘   └─────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Language & Tooling** | Python 3.11+, `uv` |
| **Database & ORM** | PostgreSQL 16, SQLAlchemy 2.0, `psycopg[binary]`, Alembic |
| **Data Contracts** | Pydantic v2 |
| **HTTP & TLS Bypass** | `curl_cffi` (Chrome impersonation) |
| **Browser Fallback** | `playwright` (stealth) |
| **HTML Parsing & Text**| `selectolax`, `trafilatura` |
| **CLI Framework** | `typer`, `rich` |

---

## Quickstart

### 1. Prerequisites & Setup
Make sure you have [uv](https://docs.astral.sh/uv/) and Docker installed.

```bash
# Clone and enter repo
cd job-scrapper

# Install dependencies into virtualenv
uv sync

# Copy environment file
cp .env.example .env

# Start local PostgreSQL 16
docker compose up -d

# Run database migrations
uv run alembic upgrade head
```

### 2. Scraping Jobs
```bash
# Scrape jobs from Himalayas posted in the last 7 days
uv run job-scrapper scrape --source himalayas --days 7

# Scrape from all configured sources
uv run job-scrapper scrape --source all --days 7
```

### 3. Exporting Datasets for ML Training
```bash
# Export recent jobs to JSONL
uv run job-scrapper export --days 7 --format jsonl --output data/jobs_dataset.jsonl

# Check database statistics
uv run job-scrapper status
```

---

## Repository Structure

```
job-scrapper/
├── pyproject.toml              # Project dependencies and CLI entry point
├── docker-compose.yml          # Local PostgreSQL container
├── alembic.ini                 # Database migrations configuration
├── migrations/                 # Alembic migration revisions
├── src/
│   └── job_scrapper/
│       ├── domain/
│       │   └── models.py       # Pydantic models (JobPosting)
│       ├── storage/
│       │   ├── base.py         # JobSink Protocol
│       │   ├── memory.py       # In-memory sink (for tests)
│       │   └── postgres/       # SQLAlchemy 2.0 models & PostgresJobSink
│       ├── pipeline/
│       │   ├── cleaner.py      # HTML to clean text extraction
│       │   ├── date_parser.py  # UTC normalization & recency filter
│       │   └── hasher.py       # SHA-256 deduplication hasher
│       ├── utils/
│       │   └── http_client.py  # Resilient curl_cffi client (jitter, rate limits)
│       ├── connectors/
│       │   ├── base.py         # Abstract BaseConnector
│       │   ├── himalayas.py    # Himalayas board connector
│       │   └── jobicy.py       # Jobicy board connector
│       ├── exporters/
│       │   └── jsonl.py        # Stream database rows to ML JSONL format
│       └── cli.py              # Typer CLI application
└── tests/                      # Minimal contract & normalization tests
```
