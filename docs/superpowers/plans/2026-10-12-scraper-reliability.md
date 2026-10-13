# Scraper Reliability Implementation Plan

> **For agentic workers:** Use the executing-plans skill to implement this plan task-by-task after the user authorizes implementation. Do not stage or commit the plan or implementation without an explicit request.

**Goal:** Adopt useful reliability ideas from ai-job-search so collection failures are visible and job records retain evidence about freshness and closure.

**Architecture:** Extend existing connector statistics, JSONB attributes, and dataset exports. Reuse the existing runner, warning display, and JobSink contract; connectors never access PostgreSQL directly.

**Tech stack:** Existing Python, Pydantic, selectolax, PostgreSQL, and React. No new dependency.

**Scope:** The user's request is a plan only. Deliver the following phases independently, starting with source health. No application assistant, candidate ranking, CV generation, or new job boards.

## Existing behavior verified

- `domain/models.py` already requires nonblank job fields and stores source, source ID, URL, publication date, scrape timestamp, and attributes.
- `storage/postgres/models.py` already stores these fields and a cross-source sightings ledger.
- `connectors/base.py` already tracks found/inserted/skipped/errors/truncation.
- `runner.py` already aggregates warnings into persisted run results.
- `cli.py` and `frontend/src/features/scraper/ScrapeRuns.jsx` already display warnings.
- `connectors/linkedin.py` flags empty first pages, repeated pages, missing dates, and invalid job fields. It does not explicitly inspect closure banners.
- `exporters/_rows.py` exports dates and source URL, but omits `source_job_id`.

Graph coverage reported changed metadata; the material source sections above were read directly before planning. This is a targeted inventory, not an exhaustive connector audit.

## Global constraints

- Preserve collection completeness; never filter jobs by candidate fit.
- Keep dynamic metadata in attributes; no database columns or migrations for new labels.
- Retain 1–3 second politeness jitter, maximum 3 concurrent requests per domain, existing curl_cffi chrome120 HTTP transport, and pre-detail deduplication.
- Zero inserted jobs can mean successful deduplication. Zero results alone cannot prove a parser is broken.
- A blocked request, missing date, or failed fetch cannot prove a job is closed.
- Keep tests within the repository's minimal domain/transform/storage policy. Use captured parser fixtures and small assert-based integration checks; no live network tests or heavy mocks.
- Prefix commands with `rtk`; use `uv` for Python execution.

## Phase 1: Make silent scraping failures visible — first priority

**Files:** `src/job_scrapper/connectors/base.py`, `src/job_scrapper/connectors/linkedin.py`, `src/job_scrapper/connectors/jobicy.py`, `src/job_scrapper/runner.py`; existing CLI/dashboard only if their warning rendering needs adjustment.

- [ ] Read Jobicy's current parser and all callers of shared statistics helpers before editing. Use LinkedIn and Jobicy as the initial pilot; do not retrofit every connector in this phase.
- [ ] Add optional diagnostic counts to pilot stats: `listing_pages`, `detail_attempted`, `detail_valid`, `detail_invalid`, and `closed`. Keep existing found/inserted/skipped meanings.
- [ ] Record invalid detail counts separately from unknown dates, outside-window jobs, closed jobs, and duplicates. Count a valid parsed posting even when storage deduplicates it.
- [ ] Add one shared pure finalization helper in `connectors/base.py`: `finalize_diagnostics(stats: dict[str, Any]) -> None`. Append a warning when listing pages were fetched but `found == 0`; describe this as unverified empty output. Append a degraded-parser warning when `detail_invalid > 0` and `detail_valid == 0`. Do not infer a problem from `inserted == 0`.
- [ ] Call the helper once in the runner after a pilot connector finishes, before final results are persisted. Skip health inference for stopped/timed-out sources. Preserve existing request errors and run-status decisions.
- [ ] Carry optional counts through progress aggregation and account aggregation where relevant; missing keys mean diagnostics are unavailable, not zero. Existing connectors remain compatible.
- [ ] Check with a small in-memory/assert-based probe: a duplicate-only run gets no parser warning; an empty listing run gets a caution; all malformed details get a warning; old dates alone do not get a malformed-parser warning; stop/timeout paths preserve their existing status.
- [ ] Verify the warning survives persistence and appears in both existing CLI and dashboard displays. Then use a bounded one-day live check of only the changed sources.

**Success:** A completed run can clearly say that output needs investigation without falsely accusing a legitimate empty source of being broken.

**Deferred:** Historical yield comparisons, automatic sentinel requests, and automatic disabling. They need comparable query/window/account scope and should follow evidence from the pilot.

## Phase 2: Capture LinkedIn closure evidence

**Files:** `src/job_scrapper/connectors/linkedin.py`, `src/job_scrapper/pipeline/job_metadata.py`, `tests/test_job_metadata.py`, captured fixtures under `tests/fixtures/linkedin/`.

- [ ] Extract a pure `parse_linkedin_closure(html: str) -> str | None` helper into the existing metadata module. Return the observed top-card closure text only when the top-card banner/class provides explicit evidence; otherwise return None. Use the existing selectolax parser.
- [ ] Add captured fixtures for an explicit closed top card, a normal posting, and a description mentioning closure while the top card remains normal. Test only this pure parser behavior.
- [ ] In `_fetch_job`, add `attributes.posting_status = 'closed'` when evidence exists, otherwise `'unknown'`; add `posting_status_evidence` only for an observed closure and `posting_status_checked_at` using the detail-fetch timestamp.
- [ ] Retain valid recent closed postings for the training dataset and increment the diagnostic `closed` counter. Missing required fields still fail the canonical JobPosting contract.
- [ ] Preserve deduplication before detail fetches. Existing known jobs are not rechecked in this phase; status describes the observed fetch, not ongoing availability.
- [ ] Verify the new attributes survive domain normalization, an InMemoryJobSink save, and export serialization. Use an explicit assertion probe for the end-to-end path.

**Success:** A posting with a real closure banner is distinguishable from a posting whose availability is unknown. Text in the job description does not create a false closure.

## Phase 3: Complete provenance in exported records

**Files:** `src/job_scrapper/exporters/_rows.py`, `src/job_scrapper/exporters/parquet.py`, `src/job_scrapper/exporters/jsonl.py` if required by its current writer; existing export documentation.

- [ ] Read both export writers and downstream references to `record_from_row` before editing.
- [ ] Add `JobModel.source_job_id` to the shared row selection and `source_job_id` to the serialized record and explicit Parquet schema. Keep existing source/URL/date fields and attributes-as-labels.
- [ ] Describe `posted_at` as the employer publication date and `scraped_at` as the stored collection timestamp. Do not rename either to last-seen or invent publication dates.
- [ ] Document that a canonical row exposes its primary source; additional source identities live in sightings. Do not place source-specific closure evidence onto another source's sighting without a separately designed storage contract.
- [ ] Generate small JSONL and Parquet exports from the same local records; assert source IDs, timestamps, and new LinkedIn metadata agree. Check that the additive export field is acceptable to any identified consumer.

**Success:** Exported training records carry the source's original job ID alongside existing URL and date provenance.

## Verification and delivery

- [ ] Run `rtk make check` after checking its current target definition. Run frontend build only if frontend code changes.
- [ ] Bound live diagnostic pagination as well as using `days=1`; the date window alone may not cap traversal.
- [ ] Review request counts and timings against the pilot baseline; diagnostics should add no network requests.
- [ ] Deliver each phase with observed checks and limitations. Keep this plan uncommitted and available for review.

## Reference material

- [Remote scraper workflow](https://github.com/MadsLorentzen/ai-job-search/blob/master/.claude/skills/job-scraper/SKILL.md): bounded health checks and explicit provenance.
- [Remote LinkedIn parser](https://github.com/MadsLorentzen/ai-job-search/blob/master/.agents/skills/linkedin-search/cli/src/helpers.ts): closure evidence scoped to the top card.

## Main limitations

Unknown availability stays unknown. Known jobs skipped by pre-fetch dedup are not revalidated. Source-specific status for merged cross-source jobs requires a later sightings design. This plan does not claim that all connectors currently have adequate diagnostics.

## Execution record — 2026-10-13

- Implemented all three phases on `feat/scraper-reliability`; nothing staged or committed.
- Ruling: Jobicy must not manufacture a title or company name when missing; canonical validation now exposes those malformed records.
- Ruling: the shared enrichment helper preserves the primary posting's availability fields. Closure evidence must not be backfilled from a different source. A minimal InMemoryJobSink regression covers both ingestion orders.
- Ruling: HTML fixtures are minimal reproductions of documented LinkedIn markup, not freshly captured closed pages. Live validation found a normal posting only.
- Validation: lint and 24 unit tests passed; `tools/check_scraper_diagnostics.py` passed. An offline integration probe exercised runner progress, warnings, stop/timeout behavior, transport-error classification, memory storage, and matching JSONL/Parquet output.
- Bounded live checks: one Jobicy page yielded 200 listings, 126 valid recent jobs, and 74 skipped; its deliberate one-page cap reported incomplete coverage. One LinkedIn listing page and one detail fetch produced a valid posting.
- Follow-up validation on 2026-10-13: Docker, API, database, and dashboard were healthy. PostgreSQL exports produced 20 matching real JSONL/Parquet rows with source IDs and timestamps. A temporary closed LinkedIn posting passed through PostgresJobSink and both exports; its transaction was rolled back and a follow-up query found zero verification rows. Persisted Jobicy counts and its warning appeared in PostgreSQL and the dashboard; CLI warning rendering passed against the saved result without submitting another scrape. `rtk make check` passed with 24 tests.
- Remaining live observation: the user's existing multi-source run was still active, with LinkedIn reporting `running` and zero jobs. The earlier bounded LinkedIn listing/detail probe succeeded, but this active run's final LinkedIn outcome is not yet known. The closed-posting HTML fixture is a minimal reproduction, not a freshly captured live closure page.

## LinkedIn progress follow-up — 2026-10-13

- The next live run showed zero until Stop because the connector waited for every first-page detail request before its first progress save. Stop cancelled queued requests; 4 completed jobs were saved and 56 cancellations were misreported as skipped.
- LinkedIn now saves listing counts immediately, saves valid jobs in groups of 10 as details finish, and flushes the remainder. Cancelled requests do not increment skipped or detail-attempted. Pending tasks are cancelled if batch persistence fails.
- `tools/check_linkedin_progress.py` passed both a stop-before-first-batch case and a ten-completions-before-one-stalled-detail case. `rtk make check` passed with 24 tests. A separate one-listing live probe was stopped after a slow upstream response; no claim is made that this follow-up was verified against a new completed live scrape.
