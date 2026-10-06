# Job Scrapper

A job scraping engine for collecting recent postings and exporting datasets for machine learning classification. The default publication window is seven days.

---

## Key Features

- **Decoupled collection**: Connectors pass `JobPosting` records through the `JobSink` protocol. PostgreSQL stores jobs; an in-memory sink supports local checks.
- **Polite requests**: `curl_cffi` uses Chrome 120 TLS impersonation, request spacing, and a limit of three concurrent requests per domain. Sites can still block requests.
- **Publication window**: General boards filter publication dates by a configurable cutoff (default: 7 days). Company ATS connectors collect all currently open jobs regardless of the cutoff.
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

Use `make cli-reset` to delete all collected jobs, sightings, and scrape-run records from the configured database. Stop scrapers first. Schema and migration history are preserved.

The CLI and Alembic both load `.env`. Process environment variables take precedence. Scraping settings are `DATABASE_URL`, `MAX_CONCURRENT_REQUESTS` (1–3), `MIN_REQUEST_DELAY_SECONDS` and `MAX_REQUEST_DELAY_SECONDS` (1–3 seconds), `REQUEST_TIMEOUT_SECONDS` (positive seconds), and `HTTP_PROXY`.

For a fresh scrape, apply schema updates with `make migrate` before starting the CLI. Existing scraped jobs may be removed when changing collection or deduplication behavior; use `make cli-reset` after stopping scrapers to clear only this project's collection and execution history. Preserve Alembic history and unrelated tables. Dashboard migrations do not require clearing existing jobs. Downgrading to the old unique-content-hash schema requires that no two jobs share a content hash.

## Local dashboard & REST API

```bash
rtk make up        # Start PostgreSQL database (or full stack in Docker)
rtk make migrate   # Apply latest database migrations
rtk make api       # Start FastAPI REST API backend (http://127.0.0.1:8000)
rtk make web       # Start React frontend development server (http://localhost:5173)
```

- **React Dashboard**: Open `http://localhost:5173`. Browse jobs with debounced search, company/source filters, server-side pagination (25, 50, or 100 rows), and slide-over job details showing full descriptions, stored attributes, multi-source sightings, and cryptographic dedup metadata.
- **REST API & Swagger Docs**: Open `http://127.0.0.1:8000/docs`. The backend provides clean OpenAPI-documented endpoints (`/api/jobs`, `/api/jobs/{id}`, `/api/runs`, `/api/session`, `/api/filters`, `/health`) with CORS support.

On **Scraper Controller**, select sources and a day window to start a background scrape. The interface reports real source/account results with explicit errors and incomplete coverage.

## Source coverage limits

The scrape CLI reports errors and incomplete coverage, then exits with status 1.

Current collection uses public JSON APIs (Himalayas, Jobicy, Arbeitnow, RemoteOK, Greenhouse, Lever, Hacker News search, and Ashby), We Work Remotely RSS, and Built In HTML pages. The Built In connector checks known IDs before fetching job pages and reads their published dates and descriptions from JobPosting metadata. Its detail requests make it slower than feed-based sources.

**Provider limits:** [Jobicy exposes a rolling seven-day feed](https://jobicy.com/jobs-rss-feed), so requests for more than seven days are incomplete. [Hacker News search uses Algolia pagination](https://hn.algolia.com/api); its index exposes at most 1,000 results per query by default. Company ATS connectors include all currently listed jobs regardless of the day window; unknown publication dates are reported as incomplete coverage.

**Scraper safety ceilings:** These are implementation choices to bound one run, not provider limits. The current caps are 500 pages for Himalayas, 500 pages for Lever, 50 pages for Arbeitnow, 500 pages for Jobicy, and 500 listing pages for Built In. If a cap is reached, the CLI marks that source incomplete. Himalayas uses the documented cursor and 20-job page size; [Lever supports `skip` and `limit`](https://github.com/lever/postings-api); [Jobicy supports cursor pagination](https://jobicy.com/jobs-rss-feed). Ashby uses its [public job-posting API](https://developers.ashbyhq.com/docs/public-job-posting-api).

### 2. Scraping Jobs
```bash
make cli-scrape
```

### 3. Exporting Datasets for ML Training
```bash
make cli-export
make cli-export format=parquet
make cli-status
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
│       │   ├── registry.py     # Source selection
│       │   ├── ashby.py        # Public employer boards
│       │   ├── builtin.py      # Public HTML listings and detail pages
│       │   └── ...             # Other API and RSS sources
│       ├── exporters/
│       │   ├── jsonl.py        # Stream database rows to JSONL
│       │   └── parquet.py      # Stream database rows to Parquet
│       └── cli.py              # Typer CLI application
└── tests/                      # Minimal contract & normalization tests
```
