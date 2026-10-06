# Job database dashboard

Status: user approved spec and implementation plan; implementation and source review complete, uncommitted. Runtime/browser validation and migration application remain pending.

## Goal and scope

Provide a local browser interface for inspecting every stored job field and starting scrapes through the existing pipeline. Build inside this repository, using the existing PostgreSQL database. Preserve existing scraper behavior and uncommitted handoff changes. Do not commit without a new request.

The approved deployment is local-only at `127.0.0.1:8000`. Remote access and login are outside this version.

## Architecture

Use FastAPI with Uvicorn to serve a small HTML/CSS/JavaScript frontend and JSON endpoints from one origin. Add dependencies through `uv`. No Node build, frontend framework, external queue, or separate worker service is needed for the first version.

Use SQLAlchemy async sessions for queries. Keep database queries outside connectors. Preserve the `JobPosting` contract and JSONB `attributes`; do not add classification columns.

Move orchestration into a shared runner consumed by CLI and web interface. Keep CLI output and exit semantics through an adapter. The runner owns cleanup and produces structured source/account results, including errors and truncation. Preserve source concurrency three and existing HTTP pacing, retries, and detail deduplication.

## Jobs interface

Use a restrained, readable operations interface: light neutral background, dark text, one accent color, clear table headings, and visible keyboard focus. Navigation has Jobs and Scrape runs. Avoid decorative charts and placeholder metrics.

The Jobs page shows total matching jobs, search, company/source filters, rows, and pagination. Rows show title, company, source, posted date, and scraped date. Search matches title/company, with a bounded query length. All filters and the current page are represented in the URL. Filter changes reset to page one.

Server-side pagination defaults to 25 rows; options are 25, 50, and 100. Validate positive page numbers and enforce a maximum page size of 100. Order by `scraped_at DESC, id DESC` for deterministic tie breaking. Return matching count and page information. Offset pagination is sufficient initially; concurrent inserts may shift page boundaries and refreshing returns current data.

Selecting a job opens an addressable detail view with:

- Full description with preserved whitespace.
- Title, company, source, original URL, posted and scraped timestamps.
- Every key/value in attributes, including nested objects and lists.
- All stored source sightings and their available fields.
- Expandable raw metadata: UUID, source job ID, content hash, canonical signature, and simhash.

Missing attributes display as unavailable, never inferred. Descriptions and values render as text, not scraped HTML. External links accept only HTTP(S), open with appropriate isolation, and unsafe values remain visible as text. Loading, empty, not-found, and database failure states are explicit. Mobile rows become readable cards and detail content reflows without horizontal page scrolling.

## Scrape controls and history

The Scrape runs page provides source selection from the registry, a positive day window (default one for development), and Start scrape. Explain that company ATS sources fetch all open jobs regardless of days. Starting requires at least one known source and returns immediately with a run identifier.

Execute a background task within a single web process. Persist a parent execution record with selected sources, day window, timestamps, status, and structured per-source/account results. Keep existing scrape-run records compatible with their current usage; inspect the lifecycle before deciding whether to extend them or add a small parent execution table. Show discovered/inserted/skipped counts only when actually reported. While a connector is running, show running state and elapsed time rather than fabricated percentages.

Poll status every three seconds only while a run is active. Completed runs remain visible after refresh or server restart. A source error or truncation yields a visible partial/failed result, with successful sources retained. Distinguish empty successful feeds from failures.

Use a PostgreSQL advisory lock held on a dedicated connection for the execution lifetime, shared by the CLI and web runner. Reject a new overlapping execution with a clear conflict message. Release in `finally`. Ensure reset refuses to run during a managed scrape. An already-running process launched before this change does not participate in the lock: finish it before validating the new runner.

On startup, mark stale dashboard executions interrupted only after determining no managed scrape owns the lock. On shutdown, cancel the background task, close connector/HTTP/database resources, and record interruption. This version has no scheduled runs or cancel button.

## Local boundary

Bind to loopback by default, allow only intended local hosts, and do not enable broad CORS. Protect mutation requests with a per-process token obtained through the same-origin UI, requiring JSON and a custom header. Reject foreign origins. Never expose credentials or pass arbitrary commands from requests. Only registered source names and validated values reach the runner.

## Commands and documentation

Add `rtk make web` to start the dashboard. Preserve `make up`/`make down` for PostgreSQL. Document the local URL and optional web dependencies in CLAUDE.md and the README using implemented behavior only. Package static assets with the Python wheel.

## Acceptance and verification

Success means browsing actual database jobs with bounded responses, reading every stored field/sighting, filtering and paging correctly, and starting a scrape without blocking navigation. The CLI must still work and overlap prevention must cover CLI, dashboard, and reset.

Follow repository testing policy: do not add network tests or broad mocked suites. Manual verification is limited to API/browser checks of paging, details, invalid input, safe text rendering, mutation protection, conflict handling, and persisted status. Any live scrape uses only a selected small source, `days=1`, with bounded traversal if necessary. Do not reset the database as part of dashboard implementation unless required and no scraper is active. No tests are run until requested; static checks may validate syntax and diffs.

## Review decisions

Approval accepts the local-only deployment, one-service stack, UI scope, and shared background-run model. After spec approval, write an implementation plan for review and execute inline in the current checkout once that plan is approved. Keep development artifacts uncommitted; remove the temporary implementation plan when its work is complete, as requested earlier.
