# Job Scrapper Implementation Plan

> **Goal**: Build an extensible, high-volume job scraper in Python targeting ~10k jobs/day, decoupled from storage, with anti-bot bypass and strict recency filtering (<= 7 days) to produce structured ML datasets.

- **Stack**: Python 3.11+, `uv`, `pydantic` v2, `SQLAlchemy 2.0`, `psycopg[binary]`, `alembic`, `curl_cffi`, `playwright`, `selectolax`, `trafilatura`, `typer`
- **Architecture**: Decoupled Extraction Engine (Producers) -> `JobSink` Protocol -> Pluggable Storage (Postgres/SQLite/File)
- **Target Initial Roles**: Software Engineering (extensible domain profile)

---

### Task 1: Project Scaffolding & Dependencies
- **Files**:
  - `pyproject.toml`
  - `.env.example`
  - `docker-compose.yml`
  - `.gitignore`
- **Actions**:
  1. Initialize Python project with `uv`.
  2. Pin dependencies: `pydantic`, `pydantic-settings`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `curl_cffi`, `selectolax`, `trafilatura`, `dateparser`, `typer`, `pytest`, `pytest-asyncio`.
  3. Create `docker-compose.yml` for local PostgreSQL 16.
  4. Create `.gitignore` and `.env.example`.
- **Verification**: `uv sync` succeeds, `docker compose up -d` starts PostgreSQL.

---

### Task 2: Domain Schema & Storage Abstraction
- **Files**:
  - `src/job_scrapper/domain/models.py`
  - `src/job_scrapper/storage/base.py`
  - `src/job_scrapper/storage/memory.py`
  - `tests/test_domain_schema.py`
- **Actions**:
  1. Define `JobPosting` Pydantic model with core fields + extensible `attributes` dict (seniority, arrangement, location, exp, salary, stack).
  2. Define `JobSink` interface (`contains(source, source_job_id) -> bool`, `save_batch(jobs: list[JobPosting]) -> int`).
  3. Implement `InMemoryJobSink` for testing.
- **Verification**: Minimal contract test verifies `InMemoryJobSink` saves and deduplicates jobs.

---

### Task 3: PostgreSQL / SQLAlchemy Storage & Alembic Migrations
- **Files**:
  - `src/job_scrapper/storage/postgres/models.py`
  - `src/job_scrapper/storage/postgres/sink.py`
  - `src/job_scrapper/storage/postgres/session.py`
  - `alembic.ini`
  - `migrations/env.py`
- **Actions**:
  1. Define SQLAlchemy `Job` table with JSONB `attributes`, `content_hash` unique index, and `(source, source_job_id)` unique constraint.
  2. Implement `PostgresJobSink` using atomic batch `INSERT ... ON CONFLICT (content_hash) DO NOTHING`.
  3. Initialize Alembic migrations and create initial migration.
- **Verification**: Run `alembic upgrade head` against Postgres.

---

### Task 4: Normalization, Cleaner & Rate-Limiter Engine
- **Files**:
  - `src/job_scrapper/pipeline/cleaner.py`
  - `src/job_scrapper/pipeline/date_parser.py`
  - `src/job_scrapper/pipeline/hasher.py`
  - `src/job_scrapper/utils/http_client.py`
- **Actions**:
  1. Implement HTML-to-clean-text using `trafilatura` / `selectolax`.
  2. Implement UTC recency parser (returns `datetime`, checks `<= max_days`).
  3. Implement SHA-256 content hasher (`company + title + description`).
  4. Implement `HttpClient` using `curl_cffi` with Chrome TLS fingerprint impersonation, configurable rate-limit jitter, and pluggable proxy support.
- **Verification**: Unit tests for date parser and content hasher.

---

### Task 5: Base Connector & First Target Connectors (Himalayas & Jobicy)
- **Files**:
  - `src/job_scrapper/connectors/base.py`
  - `src/job_scrapper/connectors/himalayas.py`
  - `src/job_scrapper/connectors/jobicy.py`
- **Actions**:
  1. Define `BaseConnector` abstract class (`scrape(sink: JobSink, max_days: int) -> int`).
  2. Implement `HimalayasConnector` (scrapes remote SE postings, parses tags, salary, location).
  3. Implement `JobicyConnector` (scrapes remote SE feed with date cutoff).
- **Verification**: Test scraping 5 sample jobs into `InMemoryJobSink` verifying recency and attribute extraction.

---

### Task 6: CLI Runner & ML Dataset Exporter
- **Files**:
  - `src/job_scrapper/cli.py`
  - `src/job_scrapper/exporters/dataset.py`
- **Actions**:
  1. Implement CLI commands using `typer`:
     - `job-scrapper scrape --source himalayas --days 7 --sink postgres`
     - `job-scrapper export --format jsonl --output data/jobs_dataset.jsonl`
  2. Build JSONL exporter streaming directly from PostgreSQL.
- **Verification**: Run live end-to-end command: scrape recent jobs and export to `data/test_dataset.jsonl`.
