# Handoff: job database dashboard

Updated: 2026-10-06
Repository: `/Users/sonukumar/project/job-scrapper`

## User request

Build a frontend to browse the scraped jobs and all fetched details, with pagination and the ability to trigger scraping from the interface.

The user approved the dashboard spec and implementation plan and requested inline execution, then requested that it be served. The dashboard is implemented in the working tree and running locally. Python compilation, JavaScript syntax, and diff whitespace checks passed. A fresh source review identified a lock-acquisition cancellation gap plus skip-link navigation and mobile wrapping issues; these were fixed. FastAPI/Uvicorn were added under the optional `web` extra. The dashboard migration is applied and HTTP readiness checks passed. No dashboard code has been committed; full functional and browser validation remains pending.

## Authorizations and constraints

- Work in the current checkout. Preserve all existing changes.
- The user authorized committing the existing changes; they are committed as `79a506e` (`Add company ATS coverage and dashboard handoff`). Nothing was pushed. Future edits still require an explicit commit request; this handoff refresh remains uncommitted.
- Scraped jobs, sightings, scrape-run records, and generated datasets are disposable. They may be reset when needed for development or validation; preserve unrelated data and services.
- Prioritize reliable, complete, efficient scraping at scale, approximately 10,000 jobs/day.
- Company ATS feeds include all currently open jobs, regardless of `--days`. General job boards retain the date cutoff.
- Use small live checks: `days=1`, selected sources, and bounded page/account counts where the date cutoff does not bound traversal.
- Use `uv` exclusively and prefix terminal commands with `rtk`. Read `AGENTS.md`, `CLAUDE.md`, and `/Users/sonukumar/.codex/RTK.md` before working.
- Keep tests minimal, following repository policy. Do not add automated live-network tests.
- Preserve connector/storage separation: connectors use `JobPosting` and `JobSink`, never database access directly.
- Keep dynamic fetched/classification fields inside `attributes`; do not add a database column per label.
- Use the codebase-memory skill for structural discovery and check coverage for relied-on files. Graph project: `Users-sonukumar-project-job-scrapper`. Verify freshness before relying on it.

## Approved dashboard implementation

Local FastAPI/Uvicorn service serving plain HTML/CSS/JavaScript and a database API from one origin. No Node build or separate frontend application. The user approved this design and the implementation plan. Spec: `docs/superpowers/specs/2026-10-06-job-dashboard-design.md`.

### Job browsing

- Server-side pagination with a stable sort, newest first.
- Search and company/source filters.
- Summary rows showing title, company, source, and dates.
- A detail view containing the full description, original posting URL, posted/scraped dates, all stored attributes, and source sightings.
- Expandable raw metadata for identifiers, hashes, and deduplication fields.
- Loading, empty, and failure states. Render scraped content safely as text.

### Scrape controls

- Select sources and the day window.
- Start a background run; do not hold an HTTP request open for the entire scrape.
- Show running/completed/failed state, counts, errors, and truncation.
- CLI, dashboard, and reset share a PostgreSQL advisory lock to prevent overlapping managed operations.
- Show previous run results.
- Reuse the existing scraping pipeline, pacing, retries, and deduplication rather than implementing another scraper.

### Deployment decision

The approved spec selects local-only at `127.0.0.1:8000`, one web process. Mutation requests require JSON, a per-process token, and same-origin checks. Remote access/login, scheduling, and a cancel button are outside this version.

## Current implementation anchors

- `src/job_scrapper/domain/models.py`: `JobPosting` contract.
- `src/job_scrapper/storage/postgres/models.py`: `JobModel`, `JobSightingModel`, `ScrapeRunModel`.
- `src/job_scrapper/storage/postgres/session.py`: database session management.
- `src/job_scrapper/storage/postgres/sink.py`: persistence and deduplication.
- `src/job_scrapper/cli.py`: `_run_scrape()` and CLI commands.
- `src/job_scrapper/runner.py`: shared structured execution, durable results, session advisory lock, and startup reconciliation.
- `src/job_scrapper/web.py`: local API, lifecycle, mutation protection, and background task startup.
- `src/job_scrapper/static/`: jobs/details and scrape history UI, responsive CSS.
- `migrations/versions/7e910c62b8fa_add_scrape_executions.py`: new parent execution table and compound jobs pagination index.
- `src/job_scrapper/connectors/registry.py`: available sources.
- `src/job_scrapper/connectors/base.py`: shared connector behavior.
- `src/job_scrapper/utils/http_client.py`: pacing, concurrency, and retries.
- `Makefile`: existing short commands including `up`, `down`, `scrape`, `status`, and `reset`.

Stored job fields include `id`, `source`, `source_job_id`, `source_url`, `title`, `company_name`, `description_text`, `posted_at`, `scraped_at`, `content_hash`, `canonical_signature`, `simhash`, and JSONB `attributes`.

The older `scrape_runs` table has no writers in the existing source. New `scrape_executions` records track an entire CLI/dashboard invocation with selected sources, days, state, timestamps, and source/account result JSON. Counts become available when a source finishes; no live percentage is invented.

`_run_scrape()` now adapts the shared runner to Rich CLI output. `run_scrape()` handles source concurrency three, HTTP/connector cleanup, persisted results, and the PostgreSQL advisory lock also used by reset. Dashboard startup reconciles stale executions only when the lock is free. Pre-change scraper processes do not hold this lock.

### Starting the dashboard

```sh
rtk make up
rtk make migrate
rtk make web
```

Open `http://127.0.0.1:8000`. Browser-backed sources additionally need `rtk uv run --extra web --extra browser job-scrapper web`. Do not use reload/multiple workers during scraping.

### Running instance and readiness evidence

- URL: `http://127.0.0.1:8000`.
- Execution session: `63887`; Uvicorn process ID reported at startup: `67291`. These identifiers belong to the originating runtime and may be stale or unavailable in a new session. Check the existing instance before starting a second server.
- Applied migration: `7e910c62b8fa` (from `4b72c4e8a1d3`), adding execution history and the pagination index. Existing jobs were preserved.
- Startup completed successfully. `GET /`, `/static/app.js`, `/api/jobs?page_size=25`, and `/api/runs` each returned HTTP 200.
- Jobs API returned 25 rows with total **10,266** at readiness check time. Runs API returned zero records; older collections are not retroactively added to execution history.
- Served using `rtk proxy env UV_CACHE_DIR=/tmp/job-scrapper-uv-cache UV_OFFLINE=1 uv run --no-sync job-scrapper web` after applying the migration with the same environment and `uv run --no-sync alembic upgrade head`.
- These are startup/readiness checks, not a complete functional test. Job details, filtering/pagination behavior, scrape triggering, lock contention, shutdown/restart recovery, and rendered browser layouts still need verification. No scrape was triggered by the readiness checks and no data was cleared.

## Committed ATS implementation

The following implementation and its coverage spec are included in commit `79a506e`:

- Catalog of 482 companies from the moreThanFAANGM directory.
- Greenhouse, Lever, Ashby, Workable, and Workday integration.
- 52 supported companies, including 41 newly enabled companies.
- Catalog totals from the completed expansion: supported 52, needs_review 419, unavailable 6, unsupported 5.
- Original directory URLs preserved; optional `board_url` identifies verified ATS endpoints.
- Workday detects exposed listing caps when a facet count exceeds the reported total, reports truncation, and avoids treating that board as a complete collection.
- Accenture, Airbus, Citi, and Target remain unresolved due to those caps. The guard does not prove the absence of caps on other boards.
- Expansion smoke checks used an in-memory sink: Affinidi 6, Contra 5, Mindtickle 19, BrowserStack 32 jobs; no errors or truncation in those checks.

Evidence/spec: `docs/superpowers/specs/2026-10-06-company-ats-coverage.md`.

Preserve this committed ATS implementation. Dashboard changes remain uncommitted and should be reviewed separately.

## Latest database collection — still pending final validation

The user requested a fresh database reset and expanded ATS test. Reset succeeded, then this command was launched:

```sh
rtk proxy env UV_CACHE_DIR=/tmp/job-scrapper-uv-cache UV_OFFLINE=1 uv run job-scrapper scrape --source greenhouse,lever,ashby,workable,workday --days 1
```

Output is redirected to `/tmp/job-scrapper-expanded-test.log`. Execution session ID in the originating tool runtime: `39127`; it may not be available in a new session.

An earlier intermediate database check observed 9,828 jobs:

| Source | Saved jobs |
| --- | ---: |
| Greenhouse | 6,576 |
| Lever | 1,367 |
| Ashby | 1,565 |
| Workable | 6 |
| Workday | 314 |

At that earlier check, blank descriptions and orphan sightings were both zero, and execution session `39127` was still running. These are **intermediate counts**, not final results. The later dashboard readiness check reported 10,266 jobs, but did not confirm collection completion or refresh the integrity checks. Check the session/process and log before launching another scrape or resetting the database. Workday detail requests can take substantially longer than feed requests.

Local PostgreSQL is configured by `docker-compose.yml`, container `job_scrapper_postgres`, database `job_scrapper`. Avoid copying credentials into the UI or exposing database access to the browser.

## Next steps

1. Check whether the expanded collection is still running; capture final account results and database integrity checks when finished.
2. Review the uncommitted dashboard code. Source review is complete; run-history queries currently load full account payloads before omitting them from summary responses, a deferred efficiency improvement.
3. The migration is already applied and the server is running. When the user requests functional verification, check API/browser behavior against the approved spec: pagination/details, safe rendering, mutation protection, nonblocking start, CLI/reset conflicts, failure/truncation, interruption/restart.
4. Use a selected small source with `days=1` for a live scraper check. Do not reset while the older collection is still active.
5. Keep all dashboard changes uncommitted until explicitly asked. Preserve the approved spec; the completed temporary implementation plan has been removed.

The user previously asked to remove temporary implementation plans once their work is complete. Retain reviewable specs and this handoff unless the user directs otherwise.
