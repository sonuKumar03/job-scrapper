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
- **REST API & Swagger Docs**: Open `http://127.0.0.1:8000/docs`. The backend provides clean OpenAPI-documented endpoints (`/api/jobs`, `/api/jobs/count`, `/api/jobs/{id}`, `/api/runs`, `/api/session`, `/api/filters`, `/health`) with CORS support. The count endpoint returns only `{"total": <job count>}`. The dashboard uses TanStack Query for shared caching, refreshes, and five-second polling of the total and run history.

On **Scraper Controller**, select sources and a day window to start a background scrape. The interface reports real source/account results with explicit errors and incomplete coverage.

## Concurrent execution

Both runtimes use the same `RunControl`, `RunStore`, `TaskTransport`, `JobSink`, and `HttpClient` ports and the same scraping worker. Runs have independent IDs and stop controls. Overlapping sources are allowed; storage still deduplicates jobs and sightings. The default is three concurrent runs and a backlog of at most 20 unfinished runs, controlled by `SCRAPE_MAX_ACTIVE_RUNS` and `SCRAPE_MAX_QUEUED_RUNS`. Running and retrying runs retain their backlog reservation, so retries cannot exceed the limit or discard accepted work.

All runs in the worker host share three source slots and one HTTP client. Per-domain concurrency stays at three, with existing 1–3 second request pacing. One worker host is supported; a database ownership lock rejects a second host. More hosts require shared domain-rate coordination first.

### Memory mode (default)

```bash
rtk make up
# Or, with the API stopped, own an embedded worker from the CLI:
rtk make cli-scrape source=jobicy,remoteok days=1 separate=1
```

The CLI or API embeds the queue and workers. The API and a scraping CLI cannot both own this runtime against the same database. Memory mode imports no Redis client and needs no broker. If the host crashes, its unfinished runs become interrupted at the next startup; already committed jobs remain saved.

### Redis broker mode

```bash
rtk make up executor=broker
rtk make cli-scrape executor=broker source=jobicy,remoteok days=1 separate=1
rtk make cli-stop run_id=<execution-uuid>
```

The optional Compose profile starts Redis and one external worker. CLI/API submit durable database dispatch intents and observe runs; they do not own scraping tasks. Local CLI connections use `redis://localhost:6379/0`; containers use `redis://redis:6379/0`. For a local worker instead of the container worker, use `rtk make cli-worker broker_url=redis://localhost:6379/0`. Never run both workers against the same database.

Direct CLI usage is `rtk uv run --extra broker job-scrapper scrape ...` with `SCRAPE_EXECUTOR=broker` and `SCRAPE_BROKER_URL` in the environment or `.env`. Each distinct database must use a distinct Redis database number or `SCRAPE_BROKER_STREAM`; sharing a stream across project databases is unsupported.

Redis uses a persistent volume, AOF with `appendfsync always`, and `noeviction`. Tasks contain only a version, run ID, and dispatch generation. Consumer acknowledgements follow committed completion or retry state; stale deliveries are skipped. The sole worker reclaims pending entries on startup. Malformed messages go to `<stream>.dead`, bounded to approximately 1,000 entries. A single Redis instance does not provide machine/disk-loss availability.

Infrastructure interruptions retry up to three attempts, waiting 5 then 30 seconds. Normal connector errors produce terminal failed/partial results rather than automatically refetching entire boards. Retried results describe the latest attempt; database counts remain authoritative. Delivery outages leave accepted work queued, with a visible dispatch delay. Stop queued work immediately; stop running work after the current batch. Ctrl+C stops only the CLI's submitted run IDs; it never shuts down an external worker.

`rtk make cli-stop` without an ID works only when exactly one run is unfinished. Reset refuses while runs are writing; idle/queued reset removes execution and dispatch records. Redis messages for deleted IDs are skipped without purging other queues. Runtime shutdown allows up to 60 seconds for cooperative cleanup; unfinished batches beyond that ceiling are interrupted. Stop/finish all unfinished runs before changing modes, then stop the old host and start the new topology. To return from broker to memory, use `rtk make down` before `rtk make up` so an old broker worker cannot retain host ownership.

The API accepts runs with HTTP 202 and status `queued`. `/api/runs/active` returns all queued/running/stopping runs plus configured capacity, independently of history pagination. The dashboard polls that endpoint every two seconds and displays per-run controls.

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
