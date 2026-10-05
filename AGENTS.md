# AGENTS.md

Instructions and architectural boundaries for AI agents operating in this repository.

---

## 1. System Purpose & Core Invariant

The purpose of this project is to collect recent job postings (posted within the last X days, default 7) from popular job boards to build training datasets for custom machine learning job classification models.

Every component must support high-volume scraping (~10k jobs/day), resilient deduplication, and export to ML-friendly formats (`.jsonl`, `.parquet`).

### Priority & Disposable Scraped Data

- The main goal is reliable, complete, and efficient scraping at scale (~10k jobs/day). Prioritize improving the scraping workflow and throughput.
- Existing scraped data is disposable. Agents may delete or reset this project's scraped jobs, sightings, scrape-run records, and generated dataset exports when required for development, fixes, or validation, without asking for additional confirmation.
- Backups, historical data recovery, and compatibility with old scraped records are not required. Scope resets to this project's scraped data and preserve unrelated databases, tables, files, and services.

---

## 2. Core Architectural Invariants

### Invariant 1: Strict Decoupling (Ports & Adapters)
- **Connectors MUST NOT touch the database**. Connectors only know about `BaseConnector` and `JobSink`.
- All extracted data must flow through the canonical Pydantic model `JobPosting` (`src/job_scrapper/domain/models.py`).
- Storage implementations (`PostgresJobSink`, `InMemoryJobSink`, `FileJobSink`) must strictly adhere to the `JobSink` protocol (`src/job_scrapper/storage/base.py`).

### Invariant 2: Extensible Classification Attributes
- Do not create a separate database column for every new classification label.
- The `JobPosting.attributes` dictionary (stored as `JSONB` in PostgreSQL) holds all dynamic classification features (`seniority`, `work_arrangement`, `location`, `salary_min`, `salary_max`, `experience_years_min`, `experience_years_max`, `tech_stack`).
- New labels must be added inside `attributes` so scrapers and downstream models can evolve without schema migrations.

### Invariant 3: Minimal Testing Policy
- **Tests must remain strictly minimal and high-signal**.
- Only test:
  1. Core domain validation (`JobPosting` contract).
  2. Pure pipeline transforms (HTML text cleaning, relative date parsing, SHA-256 content hasher).
  3. Storage contract via `InMemoryJobSink`.
- **Do NOT write flaky network tests** against live websites or write heavy mock frameworks for external boards. Use captured fixtures for parser tests.

### Invariant 4: Local IP Safety & Anti-Bot Strategy
- Scrapers run primarily from a local IP. Agents must enforce:
  1. Politeness jitter: `1.0s` to `3.0s` random delay between page requests.
  2. Concurrency limit: Maximum 3 concurrent requests per domain.
  3. Pre-fetch dedup: Call `sink.contains(source, source_job_id)` before requesting expensive detail pages.
  4. TLS spoofing: Use `curl_cffi` with `chrome120` impersonation for all HTTP requests to bypass Cloudflare 403 blocks.
  5. Browser fallback: Use `playwright` with stealth only when DOM is rendered via client-side JavaScript.

---

## 3. Tooling & Development Standards

- **Package Manager**: Use `uv` exclusively (`uv add`, `uv sync`, `uv run`).
- **Terminal Execution**: When executing terminal commands on this system, prefix all commands with `rtk ` (e.g., `rtk uv run pytest`, `rtk git status`).
- **Code Style**: Python 3.11+ type hints, Pydantic v2 schemas, SQLAlchemy 2.0 async style (`Mapped[...]`, `AsyncSession`).
