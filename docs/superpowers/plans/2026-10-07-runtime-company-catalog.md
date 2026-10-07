# Reset-safe Runtime Company Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax. Do not commit without a new explicit user request.

**Goal:** Read company targets from PostgreSQL at task start, automatically restoring packaged baseline targets whenever a database is initialized.

**Architecture:** Companies and board targets are separate records. A repository port supplies immutable target snapshots to the runner; connectors consume supplied targets and never query the database. Packaged JSON becomes initialization-only seed data, preserving the complete current runtime union.

**Tech Stack:** Existing Python 3.11+, Pydantic v2, SQLAlchemy async PostgreSQL, Alembic, Typer/FastAPI, memory/Redis execution. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-07-dynamic-company-coverage-design.md`.

## Global constraints

- Scope is stage one only: runtime catalog, seed initialization, and injected targets. Discovery, priority scheduling, and publication-date sorting require separate plans and are not delivered here.
- Preserve all 570 catalog companies and the 238 enabled provider/account pairs currently produced by catalog plus defaults. Do not call all 238 verified.
- Connectors depend on target DTOs, JobPosting, JobSink, and HttpClient; concrete database adapters stay at composition/infrastructure boundaries.
- Preserve independent runs, overlapping sources, stop/retry/reset semantics, memory/Redis parity, and existing HTTP pacing (1–3 seconds, maximum three requests per domain).
- Every shell command uses `rtk`; Python dependencies/runs use `uv`. Keep permanent tests within AGENTS.md's domain, pure-transform, and InMemoryJobSink limits. Use disposable assertion probes for infrastructure and execution integration.
- Seed every initialization without HTTP requests or overwriting runtime changes. A full database recreation restores baseline only; `cli-reset` preserves catalog tables.
- Keep specs, plans, and implementation uncommitted unless explicitly requested. Do not wipe or restart live collection to validate initialization.

## Review focus

1. A discovered account already owns a baseline pair under a different company: bootstrap preserves ownership/state and reports the conflict.
2. API and worker start together after recreation: seeding is serialized and idempotent; migration setup must not race before seeding begins.
3. A provider has zero enabled targets: report explicit no-target coverage rather than a successful empty scrape; general sources remain independent.
4. A target changes while a task runs: that task uses one immutable snapshot; subsequent tasks see the change.
5. A catalog query fails: do not fall back to the packaged list or report completion; preserve worker retry behavior for infrastructure failures.

## Files and responsibilities

- Create `src/job_scrapper/companies/contracts.py`: immutable Company, CompanyTarget, SeedReport DTOs, and CompanyTargetRepository protocol.
- Create `src/job_scrapper/companies/seed.py`: validate/load initialization seed and reconcile its rows through a supplied repository.
- Create `src/job_scrapper/companies/bootstrap.py`: shared async initialize operation and module entrypoint for migration/setup wiring.
- Create `src/job_scrapper/storage/postgres/companies.py`: repository implementation and transaction-scoped seed lock.
- Modify `storage/postgres/models.py` and add migration `migrations/versions/<generated>_add_company_targets.py`: company and board schema only.
- Rename `src/job_scrapper/company_sources.json` to `src/job_scrapper/company_seed.json`: package seed data, including default-only boards.
- Remove `connectors/company_sources.py` after its validation has moved to the seed boundary.
- Modify the five ATS connectors, `connectors/registry.py`, `runner.py`, and `execution/bootstrap.py`: explicit target injection.
- Modify `cli.py`, `Makefile`, `docker-compose.yml`, and `readme.md`: initialize and seed all supported boot paths, update coverage reporting.
- Disposable probes go under `/private/tmp`; no production test framework or permanent network suite.

### Task 1: Define targets and preserve the baseline

**Interfaces:** Produce frozen `Company(company_key, company_name, source_url)` and `CompanyTarget(company_key, company_name, provider, account_key, board_url, verification_status, enabled)` DTOs. `CompanyTargetRepository` exposes `ensure_seed(companies: tuple[Company, ...], targets: tuple[CompanyTarget, ...]) -> SeedReport`, `list_enabled(provider: str) -> tuple[CompanyTarget, ...]`, and `status_counts() -> dict[str, int]`, all async. SeedReport contains counts of inserted companies/targets and conflicts, without ORM objects.

- [x] Capture current JSON and the union of each connector's default targets into a disposable baseline manifest. Assert 570 original company records, 200 supported catalog accounts, and 238 distinct enabled runtime provider/account pairs.
- [x] Write a failing disposable seed-loading probe asserting preserved original source URLs, preserved names for catalog-derived targets, unique company keys and account pairs, multiple boards for one company, and distinct status/enabled values for default-only accounts.
- [x] Define DTOs/protocol in `companies/contracts.py` and `load_seed() -> tuple[tuple[Company, ...], tuple[CompanyTarget, ...]]` in `companies/seed.py`. Validate nonempty text, provider membership, absolute public board URLs, and account syntax; keep unresolved records as companies even when they have no known board.
- [x] Convert the packaged JSON into a versioned seed object with company and board arrays. Include the 38 additional enabled default accounts. Associate a default account with an existing company only from explicit identity evidence; otherwise use a deterministic `provider-account` company key. Do not delete or rename the 570 original keys.
- [x] Run the seed probe and existing domain/pipeline tests. Confirm no network/database access during load and no runtime connector depends on the new loader yet.

### Task 2: Add database schema and idempotent repository

**Interfaces:** Produce `PostgresCompanyTargetRepository(manager)` satisfying Task 1's protocol. `CompanyCatalogUnavailable` is an infrastructure exception exposed by the port boundary, preserving the original cause in internal diagnostics.

- [x] Write a failing disposable PostgreSQL probe against an isolated project database, covering multiple boards per company, unique provider/account pairs, repeated seed, simultaneous seed calls, and runtime disable/name/status preservation.
- [x] Add `CompanyModel` (`company_key` primary key, name, source URL) and `CompanyTargetModel` (UUID primary key, company foreign key, provider/account unique pair, board URL, status, enabled, provenance, nullable checked/succeeded timestamps and last error). Add an index supporting enabled/provider lookup. Dynamic classification fields remain in JobPosting.attributes, not these tables.
- [x] Generate and implement the next Alembic revision after `91c42e7a6b30`. Upgrade creates only catalog tables/indexes; downgrade removes only these tables. No job/run rewrite or data reset.
- [x] Implement `ensure_seed` as one transaction with a dedicated transaction-scoped advisory lock and insert-if-missing operations. Compare existing company/board values for conflict diagnostics; never change an existing board's company association or runtime fields. Concurrent discoveries are protected by unique constraints and conflict handling. Do not create orphan company rows beyond intentional missing seed companies.
- [x] Implement enabled snapshot queries joined to companies with deterministic provider/account order; map query/commit infrastructure failures to CompanyCatalogUnavailable. Do not expose ORM sessions through the protocol.
- [x] Run migrations and probes against the isolated database. Assert a second seed inserts zero rows, disabled targets remain disabled, alternate ownership remains intact, and original seed URLs are restored after complete isolated database recreation.

### Task 3: Seed every database initialization path

**Interfaces:** Produce `initialize_company_catalog(manager: DatabaseSessionManager) -> SeedReport` in the composition layer, using `load_seed` plus PostgresCompanyTargetRepository. Produce module command `rtk uv run python -m job_scrapper.companies.bootstrap` for setup; it seeds an already migrated database and closes its engine on success/failure.

- [x] Write a failing isolated initialization probe exercising migrations followed by initialization, repeated initialization, an existing head migration with empty catalog tables, and seed failure before workers start.
- [x] Invoke shared initialization in `execution_runtime` before constructing/startup of transports, dispatchers, and workers. API and CLI scrape share this path; external worker uses it too. Invalid seed or missing schema stops bootstrap clearly; do not auto-create ORM tables outside migrations.
- [x] Update `make migrate` to run Alembic followed by shared initialization. `make setup` already calls migrate and must therefore populate the seed.
- [x] Ensure Compose applies schema exactly once before API/worker startup. Use a one-shot migration/seed service with `service_completed_successfully` dependencies for API and broker worker rather than concurrent Alembic commands in both services. Keep existing profiles, bind mounts, and database settings. Repeated `make up` must not skip initialization of a recreated database; runtime bootstrap remains the final idempotent guarantee.
- [x] Keep `cli-reset`'s explicit job/run table list unchanged. Confirm it preserves companies/boards; verify full isolated database recreation plus migrate restores all baseline targets. No live DB reset.
- [x] Verify simultaneous API/worker initialization cannot produce duplicate records and invalid seed prevents collection from beginning. Document raw `alembic upgrade head` versus the full `make migrate` initialization command.

### Task 4: Inject snapshots into all five ATS connectors

**Interfaces:** ATS constructors accept `targets: tuple[CompanyTarget, ...]` and existing HTTP kwargs. `get_connector(name: str, http_client: HttpClient | None = None, *, company_targets: tuple[CompanyTarget, ...] | None = None) -> BaseConnector` validates that ATS callers supply a snapshot. General connectors ignore no catalog state and keep their current construction behavior. Runner consumes `CompanyTargetRepository` through a supplied application dependency, not PostgreSQL imports.

- [x] Write failing captured-parser probes for Greenhouse, Lever, Ashby, Workday, and Workable using explicit target DTOs/InMemoryJobSink. Pin company names, namespaced IDs, Workday host derived from its board URL, repeat-ingestion deduplication, and empty-target diagnostics.
- [x] Replace catalog/default loading in the five constructors with target snapshots. Remove connector-owned default lists only after Task 1 baseline assertions pass. Preserve parsers, request safety, date semantics, per-account reporting, and explicit target injection for manual checks.
- [x] Update registry factory and runner injection. Resolve enabled targets exactly once after source capacity is acquired and before connector creation. Capture immutable rows for that provider task; do not re-query inside account/page loops.
- [x] In execution bootstrap, construct the repository and supply it to the shared pipeline using the existing callable/partial pattern. Keep WorkerPool's transport and task lifecycle unchanged. Both runtime modes use the same path.
- [x] When an ATS snapshot is empty, report `no enabled company targets` as explicit incomplete/failed coverage without HTTP requests. When repository access fails, propagate CompanyCatalogUnavailable beyond the per-source connector-error handler so the common worker uses its infrastructure retry policy; never silently fall back to JSON.
- [x] Replace CLI's JSON catalog summary with repository status counts, labeling company versus board totals and verification separately. Reporting errors must not turn a completed scrape into an automatic whole-run retry.
- [x] Remove the old loader module and verify no runtime references remain. Run captured checks, mutation-during-run probe, and repository-failure probe in both memory and Redis worker contexts.

### Task 5: Verify complete boot/reset and collection paths

- [x] Run `rtk uv run pytest tests/`; expected all current minimal tests pass.
- [x] Check a fresh isolated database: 570 original company keys are present, all original URLs preserved, all 238 baseline runtime target pairs enabled, and catalog/default verification counts are distinct. Repeat bootstrap and assert no inserts/state changes.
- [x] Disable one baseline board and add a second board to an existing company through the repository in the isolated environment. Restart bootstrap; assert both changes persist and only enabled boards reach the next provider snapshot.
- [x] Exercise CLI reset, then full isolated recreation. First preserves runtime targets; second restores the baseline and removes isolated discoveries. Never alter unrelated tables or services.
- [x] Validate API source listing, CLI source validation, memory scrape and Redis external-worker scrape using bounded captured/local scenarios. Confirm stop, retry, queued runs, and no-worker broker submission still behave as before.
- [x] Run selected one-day live checks with InMemoryJobSink and injected verified target snapshots only after other network probes finish; bound Workday details/pages. Record parser failures honestly, separate from repository validation. No permanent network tests or frontend production build.
- [x] Update readme with runtime catalog, automatic reset seeding, 200 verified plus 38 preserved defaults, catalog state reset behavior, and the fact discovery/scheduling remain future stages. Mark the old company-ATS spec as historical where its runtime-loading description no longer applies.
- [x] Run `rtk git diff --check`, inspect scoped diff and remaining loader/default references, obtain a focused final review, and leave changes uncommitted.

## Subsequent independent stages

The overall spec is not complete when this plan finishes. Next write a discovery/control plan covering actual application-URL retention in each supported general board, safe ATS URL extraction, disabled candidate persistence, exact provider verification rules, CLI/web controls, and bounded execution through shared ports. Then resolve mixed-run admission and write a scheduling plan before changing worker lifecycle; reserving a source semaphore alone is not acceptable. Publication-date ordering is an independent focused change.

## Execution handoff

Recommended method: native implementation in this session followed by one independent final review. The tasks share DTOs, migration/bootstrap state, and all five connector constructors; sequential execution avoids simultaneous incompatible interfaces. Review and approve this plan before implementation. No commits are authorized by plan approval.
