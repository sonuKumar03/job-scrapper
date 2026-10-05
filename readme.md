# Job Scrapper

A job scraping engine for collecting recent postings and exporting datasets for machine learning classification. The default publication window is seven days.

---

## Key Features

- **Decoupled collection**: Connectors pass `JobPosting` records through the `JobSink` protocol. PostgreSQL stores jobs; an in-memory sink supports local checks.
- **Polite requests**: `curl_cffi` uses Chrome 120 TLS impersonation, request spacing, and a limit of three concurrent requests per domain. Sites can still block requests.
- **Strict Recency Filtering**:
  - Automatically filters and normalizes publication dates into UTC, dropping postings older than a configurable cutoff (default: 7 days).
- **Extensible Classification Schema**:
  - Core canonical fields (`title`, `company_name`, `description_text`, `posted_at`) paired with a flexible `attributes` JSON payload (`seniority`, `work_arrangement`, `location`, `salary_min`, `salary_max`, `experience_years_min`, `experience_years_max`, `tech_stack`).
  - Add or modify classification labels without database migrations.
- **Dataset export**: Stream PostgreSQL rows in batches to `.jsonl` or `.parquet`. A successful export atomically replaces the destination.

---

## Architecture

Job boards → connectors → `JobPosting` → `PostgresJobSink` → PostgreSQL → JSONL or Parquet exporter.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Language & Tooling** | Python 3.11+, `uv` |
| **Database & ORM** | PostgreSQL 16, SQLAlchemy 2.0, `psycopg[binary]`, Alembic |
| **Data Contracts** | Pydantic v2 |
| **HTTP & TLS** | `curl_cffi` (Chrome impersonation) |
| **HTML Parsing & Text**| `selectolax`, `trafilatura` |
| **CLI Framework** | `typer`, `rich` |

---

## Quickstart

### 1. Prerequisites & Setup
Make sure you have [uv](https://docs.astral.sh/uv/) and Docker installed.

```bash
make setup
```

Use `make up` to start PostgreSQL again and `make down` to stop it.

Use `make reset` to delete all collected jobs, sightings, and scrape-run records from the configured database. Stop scrapers first. Schema and migration history are preserved.

The CLI and Alembic both load `.env`. Process environment variables take precedence. Scraping settings are `DATABASE_URL`, `MAX_CONCURRENT_REQUESTS` (1–3), `MIN_REQUEST_DELAY_SECONDS` and `MAX_REQUEST_DELAY_SECONDS` (1–3 seconds), `REQUEST_TIMEOUT_SECONDS` (positive seconds), and `HTTP_PROXY`.

For a fresh scrape, apply schema updates with `make migrate` before starting the CLI. Existing scraped jobs may be removed when changing collection or deduplication behavior; if clearing them, pause scrapers and truncate only `job_sightings`, `jobs`, and `scrape_runs` in the explicitly configured project database. Preserve Alembic history and unrelated tables. The current migration does not require clearing existing rows. Downgrading to the old unique-content-hash schema requires that no two jobs share a content hash.

## Source coverage limits

The scrape CLI reports errors and incomplete coverage, then exits with status 1.

**Provider limits:** [Jobicy exposes a rolling seven-day feed](https://jobicy.com/jobs-rss-feed), so requests for more than seven days are incomplete. [Hacker News search uses Algolia pagination](https://hn.algolia.com/api); its index exposes at most 1,000 results per query by default. Greenhouse jobs without the API's original [`first_published` date](https://docs.greenhouse.io/job-board.html) are skipped and counted as unknown.

**Scraper safety ceilings:** These are implementation choices to bound one run, not provider limits. The current caps are 500 pages for Himalayas, 500 pages for Lever, 50 pages for Arbeitnow, and 500 pages for Jobicy. If a cap is reached, the CLI marks that source incomplete. Himalayas uses the documented cursor and 20-job page size; [Lever supports `skip` and `limit`](https://github.com/lever/postings-api); [Jobicy supports cursor pagination](https://jobicy.com/jobs-rss-feed).

### 2. Scraping Jobs
```bash
make scrape
```

### 3. Exporting Datasets for ML Training
```bash
make export
make parquet
make status
```

Parquet stores `labels` as a UTF-8 JSON string so postings with different attribute keys share one schema. JSONL keeps `labels` as a JSON object. Both exports write 500-row batches and replace the destination only after a successful write.

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
│       │   ├── jsonl.py        # Stream database rows to JSONL
│       │   └── parquet.py      # Stream database rows to Parquet
│       └── cli.py              # Typer CLI application
└── tests/                      # Minimal contract & normalization tests
```
