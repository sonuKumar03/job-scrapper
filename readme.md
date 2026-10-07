# Job Scrapper

A job scraping engine for collecting recent postings and exporting datasets for machine learning classification. The default publication window is seven days.

---

## Key Features

- **Decoupled collection**: Connectors pass `JobPosting` records through the `JobSink` protocol. PostgreSQL stores jobs; an in-memory sink supports local checks.
- **Polite requests**: `curl_cffi` uses Chrome 120 TLS impersonation, request spacing, and a limit of three concurrent requests per domain. Sites can still block requests.
- **Publication window**: General boards filter publication dates by a configurable cutoff (default: 7 days). Company ATS connectors collect all currently open jobs regardless of the cutoff.
- **Company coverage**: PostgreSQL supplies runtime targets for Greenhouse, Lever, Ashby, Workday, and Workable. Initialization restores 200 verified catalog mappings plus 38 previously enabled provider defaults; those defaults are not newly verified. Per-account results report failures, missing dates, and incomplete collection.
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

Prerequisites: Docker with Compose v2 and Make. Native Python commands additionally need uv and Python 3.11+; native frontend work needs Node 22/npm. RTK is not required for contributors.

### Development containers

```sh
make up                 # Full stack at http://localhost:3000
make up executor=broker # Redis and one external worker
make down               # Stop services; keep volumes
```

This is a development stack with source mounts and API reload. Stop it before running native servers on the same ports or changing modes.

### Native development

```sh
make setup              # Frozen dependencies, PostgreSQL, migration and seed
make api                # http://127.0.0.1:8000
# Another terminal:
make web                # http://localhost:3000
```

Keep container API/worker services stopped. Memory mode permits one worker-owning CLI/API process against a database; stop the API before a native memory scrape. Use `make check` for correctness lint and unit tests and `make web-build` for the frontend build.

### Deployment

The deployment target is Vercel for the frontend, Railway for the API and one external scraping worker, and separate PostgreSQL and Redis services. The backend production image uses locked dependencies and runs as a non-root user. See [operations](docs/operations.md) for configuration, initialization, health, and recovery.

Public deployment still needs an authentication boundary: the request token is not user authentication. Cloud deployment has not been verified yet.

The CLI and Alembic load `.env`; process environment wins. Request settings constrain per-domain concurrency to 1–3 and delays to 1–3 seconds. `make migrate` applies schema and inserts missing seed records. `make cli-reset` removes scraped jobs/sightings/run history while retaining company configuration and migration history; stop scrapers first. Full database recreation restores only the packaged company baseline.

### Company targets and database resets

`make migrate` applies schema updates and seeds missing company records. Compose runs one migration/seed service before the API or broker worker starts. API, CLI scrape, and worker startup also repeat the idempotent seed operation, so an already migrated database with empty catalog tables is repopulated.

The packaged `company_seed.json` is bootstrap data only; connectors receive an immutable database target snapshot when their provider task starts. Companies and board targets are separate records, allowing multiple boards per employer. The initial seed contains 608 company identities (all 570 previous catalog records plus 38 default-specific identities) and 248 boards, of which 238 are enabled. Disabled/unresolved boards are retained for review. The CLI's all-source summary distinguishes companies, boards, enabled boards, and verification statuses.

Seeding inserts missing rows without overwriting runtime names, board ownership, enabled flags, or verification results. Conflicting seed mappings are reported and existing mappings are preserved. `cli-reset` leaves this configuration intact. After a full database wipe, migrate/initialization restores the packaged baseline; additional runtime discoveries and edits are lost. Raw `alembic upgrade head` creates schema only; use `make migrate` for complete initialization or follow it with `uv run python -m job_scrapper.companies.bootstrap`.

This stage provides the database catalog and reset-safe seed. Automatic company discovery, catalog-management UI, priority scheduling, and publication-date sorting are not implemented yet. The current UI continues to show collected jobs in collection order.

## Attribute normalization

Every connector's `JobPosting` passes through the pure `pipeline.attributes.normalize_attributes` transform before storage. It normalizes explicit work arrangements (`remote`, `hybrid`, `in-office`, `unknown`), employment types, and nonnegative numeric experience bounds. Custom attributes remain intact; `_attribute_evidence` records the original value, extraction method, and normalized result.

Structured source values take priority. Missing fields may use explicitly labeled work/employment text or unambiguous required-experience text from descriptions. Ambiguous labels become unknown; invalid or reversed experience bounds become null. These conservative rules do not infer seniority, salary, locations, or technologies. They apply to newly created postings; existing stored records are not rewritten. Connectors remain responsible for mapping source-specific fields, and deduplication retains evidence for backfilled attributes.

## Dashboard and REST API

The dashboard supports debounced search, source/company filters, pagination, job details, and per-run start/stop controls. Both native and development-container frontends use port 3000. Native/development API documentation is at http://127.0.0.1:8000/docs.

The API includes `/api/jobs`, `/api/jobs/count`, `/api/jobs/{id}`, `/api/runs`, `/api/runs/active`, `/api/session`, and `/api/filters`. TanStack Query shares cached data; counts/history poll every five seconds and active runs every two seconds. `/health` checks liveness; `/ready` checks PostgreSQL and local execution admission. Broker API readiness does not certify Redis or the external worker. The frontend supports `VITE_API_URL` for a separate API, or same-origin `/api` requests through a hosting rewrite.

## Concurrent execution

Both runtimes use the same `RunControl`, `RunStore`, `TaskTransport`, `JobSink`, and `HttpClient` ports and the same scraping worker. Runs have independent IDs and stop controls. Overlapping sources are allowed; storage still deduplicates jobs and sightings. The default is three concurrent runs and a backlog of at most 20 unfinished runs, controlled by `SCRAPE_MAX_ACTIVE_RUNS` and `SCRAPE_MAX_QUEUED_RUNS`. Running and retrying runs retain their backlog reservation, so retries cannot exceed the limit or discard accepted work.

All runs in the worker host share three source slots and one HTTP client. Per-domain concurrency stays at three, with existing 1–3 second request pacing. One worker host is supported; a database ownership lock rejects a second host. More hosts require shared domain-rate coordination first.

### Memory mode (default)

```bash
make up
# Or, with the API stopped, own an embedded worker from the CLI:
make cli-scrape source=jobicy,remoteok days=1 separate=1
```

The CLI or API embeds the queue and workers. The API and a scraping CLI cannot both own this runtime against the same database. Memory mode imports no Redis client and needs no broker. If the host crashes, its unfinished runs become interrupted at the next startup; already committed jobs remain saved.

### Redis broker mode

```bash
make up executor=broker
make cli-scrape executor=broker source=jobicy,remoteok days=1 separate=1
make cli-stop run_id=<execution-uuid>
```

The optional Compose profile starts Redis and one external worker. CLI/API submit durable database dispatch intents and observe runs; they do not own scraping tasks. Local CLI connections use `redis://localhost:6379/0`; containers use `redis://redis:6379/0`. For a local worker instead of the container worker, use `make cli-worker broker_url=redis://localhost:6379/0`. Never run both workers against the same database.

Direct CLI usage is `uv run --extra broker job-scrapper scrape ...` with `SCRAPE_EXECUTOR=broker` and `SCRAPE_BROKER_URL` in the environment or `.env`. Each distinct database must use a distinct Redis database number or `SCRAPE_BROKER_STREAM`; sharing a stream across project databases is unsupported.

Redis uses a persistent volume, AOF with `appendfsync always`, and `noeviction`. Tasks contain only a version, run ID, and dispatch generation. Consumer acknowledgements follow committed completion or retry state; stale deliveries are skipped. The sole worker reclaims pending entries on startup. Malformed messages go to `<stream>.dead`, bounded to approximately 1,000 entries. A single Redis instance does not provide machine/disk-loss availability.

Infrastructure interruptions retry up to three attempts, waiting 5 then 30 seconds. Normal connector errors produce terminal failed/partial results rather than automatically refetching entire boards. Retried results describe the latest attempt; database counts remain authoritative. Delivery outages leave accepted work queued, with a visible dispatch delay. Stop queued work immediately; stop running work after the current batch. Ctrl+C stops only the CLI's submitted run IDs; it never shuts down an external worker.

`make cli-stop` without an ID works only when exactly one run is unfinished. Reset refuses while runs are writing; idle/queued reset removes execution and dispatch records. Redis messages for deleted IDs are skipped without purging other queues. Runtime shutdown allows up to 60 seconds for cooperative cleanup; unfinished batches beyond that ceiling are interrupted. Stop/finish all unfinished runs before changing modes, then stop the old host and start the new topology. To return from broker to memory, use `make down` before `make up` so an old broker worker cannot retain host ownership.

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
├── docker-compose.yml          # Development stack
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

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, architecture boundaries, and checks, and [SECURITY.md](SECURITY.md) for the deployment security boundary and pending security-report channel. Code is licensed under [MIT](LICENSE). CI configuration is included; hosted status requires a configured GitHub remote and push.
