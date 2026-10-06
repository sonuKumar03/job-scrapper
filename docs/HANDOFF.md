# Handoff: job database dashboard

Updated: 2026-10-06
Repository: `/Users/sonukumar/project/job-scrapper`

## User request

Build a frontend to browse the scraped jobs and all fetched details, with pagination and the ability to trigger scraping from the interface.

The user requested this handoff before implementation. No dashboard code has been written, no dependencies installed, and no dashboard design or implementation plan has been approved.

## Authorizations and constraints

- Work in the current checkout. Preserve all existing changes.
- **Do not stage or commit anything until explicitly asked.** This includes documentation.
- Scraped jobs, sightings, scrape-run records, and generated datasets are disposable. They may be reset when needed for development or validation; preserve unrelated data and services.
- Prioritize reliable, complete, efficient scraping at scale, approximately 10,000 jobs/day.
- Company ATS feeds include all currently open jobs, regardless of `--days`. General job boards retain the date cutoff.
- Use small live checks: `days=1`, selected sources, and bounded page/account counts where the date cutoff does not bound traversal.
- Use `uv` exclusively and prefix terminal commands with `rtk`. Read `AGENTS.md`, `CLAUDE.md`, and `/Users/sonukumar/.codex/RTK.md` before working.
- Keep tests minimal, following repository policy. Do not add automated live-network tests.
- Preserve connector/storage separation: connectors use `JobPosting` and `JobSink`, never database access directly.
- Keep dynamic fetched/classification fields inside `attributes`; do not add a database column per label.
- Use the codebase-memory skill for structural discovery and check coverage for relied-on files. Graph project: `Users-sonukumar-project-job-scrapper`. Verify freshness before relying on it.

## Dashboard proposal — not yet approved

Recommended first version: a local Python web service serving both the UI and database API. A separate frontend application remains an option; no framework has been selected.

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
- Prevent overlapping runs through the dashboard. Decide how to coordinate with CLI runs too.
- Show previous run results.
- Reuse the existing scraping pipeline, pacing, retries, and deduplication rather than implementing another scraper.

### Pending question

An asynchronous question was sent asking whether this should be **local-only** or **remotely accessible with login**. No answer has arrived in the conversation yet.

Local-only is the recommendation, not an approved requirement. Remote access requires authentication and appropriate protection for scrape-triggering endpoints. Even a local service should bind to loopback and protect mutation endpoints from unintended browser requests.

## Current implementation anchors

- `src/job_scrapper/domain/models.py`: `JobPosting` contract.
- `src/job_scrapper/storage/postgres/models.py`: `JobModel`, `JobSightingModel`, `ScrapeRunModel`.
- `src/job_scrapper/storage/postgres/session.py`: database session management.
- `src/job_scrapper/storage/postgres/sink.py`: persistence and deduplication.
- `src/job_scrapper/cli.py`: `_run_scrape()` and CLI commands.
- `src/job_scrapper/connectors/registry.py`: available sources.
- `src/job_scrapper/connectors/base.py`: shared connector behavior.
- `src/job_scrapper/utils/http_client.py`: pacing, concurrency, and retries.
- `Makefile`: existing short commands including `up`, `down`, `scrape`, `status`, and `reset`.

Stored job fields include `id`, `source`, `source_job_id`, `source_url`, `title`, `company_name`, `description_text`, `posted_at`, `scraped_at`, `content_hash`, `canonical_signature`, `simhash`, and JSONB `attributes`.

Scrape-run records include source, start/finish timestamps, status, found/inserted counts, and error message. Inspect their actual persistence lifecycle before using them as dashboard progress: their schema alone does not establish that every connector writes useful live progress.

`_run_scrape()` currently owns HTTP/database resources, runs up to three sources concurrently, prints Rich output, and returns a failure boolean. It is not yet a structured web-facing runner. Design the smallest shared execution boundary needed for CLI and dashboard consumers, preserving cleanup and failure behavior.

## Existing ATS work awaiting user review

All of the following is uncommitted:

- Catalog of 482 companies from the moreThanFAANGM directory.
- Greenhouse, Lever, Ashby, Workable, and Workday integration.
- 52 supported companies, including 41 newly enabled companies.
- Catalog totals from the completed expansion: supported 52, needs_review 419, unavailable 6, unsupported 5.
- Original directory URLs preserved; optional `board_url` identifies verified ATS endpoints.
- Workday detects exposed listing caps when a facet count exceeds the reported total, reports truncation, and avoids treating that board as a complete collection.
- Accenture, Airbus, Citi, and Target remain unresolved due to those caps. The guard does not prove the absence of caps on other boards.
- Expansion smoke checks used an in-memory sink: Affinidi 6, Contra 5, Mindtickle 19, BrowserStack 32 jobs; no errors or truncation in those checks.

Evidence/spec: `docs/superpowers/specs/2026-10-06-company-ats-coverage.md`.

Do not overwrite or commit these changes as part of dashboard work.

## Latest database collection — still pending final validation

The user requested a fresh database reset and expanded ATS test. Reset succeeded, then this command was launched:

```sh
rtk proxy env UV_CACHE_DIR=/tmp/job-scrapper-uv-cache UV_OFFLINE=1 uv run job-scrapper scrape --source greenhouse,lever,ashby,workable,workday --days 1
```

Output is redirected to `/tmp/job-scrapper-expanded-test.log`. Execution session ID in the originating tool runtime: `39127`; it may not be available in a new session.

Last database check observed 9,656 jobs:

| Source | Saved jobs |
| --- | ---: |
| Greenhouse | 6,576 |
| Lever | 1,367 |
| Ashby | 1,565 |
| Workable | 6 |
| Workday | 142 |

At that check, blank descriptions and orphan sightings were both zero. These are **intermediate counts**, not final results. At handoff creation, the log still only showed source-start messages through Workday; completion was not confirmed. Check the process and log before launching another scrape or resetting the database. Workday detail requests can take substantially longer than feed requests.

Local PostgreSQL is configured by `docker-compose.yml`, container `job_scrapper_postgres`, database `job_scrapper`. Avoid copying credentials into the UI or exposing database access to the browser.

## Next steps

1. Check whether the expanded collection is still running; capture final account results and database integrity checks when finished.
2. Resolve local-only versus remote access with the user.
3. Present the dashboard design, including pagination, fields, background execution, overlap prevention, progress persistence, and failure handling.
4. Follow the brainstorming skill's architectural workflow: approved design, written spec review, then implementation plan review before implementation. Keep these artifacts uncommitted, overriding the skill's default commit instruction.
5. Build the smallest approved dashboard using existing storage and scraper code. Do not introduce queues, separate workers, or a second frontend build without a demonstrated need.
6. Verify the approved behavior with focused checks and browser inspection. Use the existing Chrome session when applicable.

The user previously asked to remove temporary implementation plans once their work is complete. Retain reviewable specs and this handoff unless the user directs otherwise.
