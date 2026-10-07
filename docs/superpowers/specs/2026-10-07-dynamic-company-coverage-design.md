# Dynamic company coverage and reset-safe initialization

## Delivery status (2026-10-07)

Stage one is implemented and uncommitted: database company/board records, initialization-only seed, idempotent startup population, and injected snapshots for all five ATS providers. The baseline preserves 570 original company records and the exact 238 enabled account union; separate identities for 38 defaults produce 608 seeded companies and 248 board records total. CLI reset retains runtime configuration, while full recreation restores the baseline.

Validation covered isolated repeated/concurrent initialization, ownership and disabled-state preservation, full recreation, CLI reset, multiple boards per company, missing-database failure, and actual CLI/API collection in memory and Redis modes using captured feeds. All five parsers passed repeat-ingestion checks. Selected live checks saved 136 jobs in memory, including one Workday posting with intentionally bounded listing/detail traversal; that Workday check correctly reported its one-page safety ceiling. Existing project tests passed and independent review found no Critical or Important issues.

Discovery/management controls, capacity reservation, and publication-date ordering remain separate future stages. Database-backed targets alone do not discover new companies or change scheduling.

## Purpose

Remove the fixed runtime company-target list while preserving the 200 verified mappings. Allow coverage to grow through verified discoveries without editing application configuration, and prevent long company-board runs from delaying recent general-board collection. Database resets are routine: every fresh initialization must automatically restore baseline company coverage.

## Selected approach

Use PostgreSQL as the runtime catalog and retain the packaged JSON as bootstrap data only. Moving targets into environment variables would remain a manually maintained fixed list. Automatically crawling arbitrary careers pages would add substantial cost and uncertainty; instead discover supported ATS accounts from known public job URLs first.

This does not promise unlimited coverage or create a periodic scrape schedule by itself. Existing manually submitted runs remain supported in memory and Redis modes.

## Catalog and boundaries

- Introduce a company-target repository port in the application/domain boundary, implemented by PostgreSQL. Connectors receive immutable target snapshots and never access the repository or database themselves.
- Separate companies from board targets: a company has a unique stable key, employer name, and original source URL; it may have several regional or provider boards. Each board stores provider, account key, board URL, verification state, an independent enabled flag, provenance, and nullable check/success timestamps and failure information.
- Enforce unique company keys and unique provider/account pairs on boards. Do not merge companies solely because display names resemble each other. Validation must reject unsupported providers, malformed accounts, and invalid board URLs before enabling a newly discovered target.
- Preserve all 570 existing company records, including unresolved directory records. Merge existing provider defaults into bootstrap data without dropping accounts: the current runtime union is 238 distinct provider/account pairs, comprising 200 supported catalog mappings and 38 default-only accounts. Default-only accounts retain their current enabled behavior and have unverified provenance; they must not be presented as 238 verified boards. Attach additional accounts to an existing company only when identity is explicit; otherwise use a distinct provider/account-derived company key.
- Remove connector-owned fallback lists after their entries are preserved in the seed. Explicit injected target lists remain available for captured-parser and in-memory checks.
- Resolve a target snapshot when a provider task begins, so updates apply to subsequent tasks without changing the targets midway through a running task. Database catalog failures are visible task failures, not silent empty-board success.

## Initialization and resets

- Add the catalog schema through the existing migration mechanism. Follow schema initialization with one shared, transactional seed operation used by CLI, API, and external-worker bootstrap.
- Seed on every initialization using insert-if-missing semantics and database uniqueness constraints. Repeating or concurrently attempting initialization must create no duplicates and must not overwrite enabled flags, verification results, or discovered mappings.
- Existing provider/account ownership wins over a seed's proposed company association. If a discovered board already occupies that pair, preserve its company association and runtime fields, and report a seed conflict; never create a duplicate board or silently reparent it. A conflicting company key also preserves existing values. Distinct missing company records may still be inserted, even when their baseline board already belongs to another company. Serialize seed transactions with a dedicated transaction-scoped advisory lock; a conflict is diagnostic, while malformed packaged seed data is a fatal initialization error.
- Fresh databases restore all baseline records automatically; no separate manual seed command is required. Seeding makes no external HTTP requests.
- `make migrate` and fresh Compose startup must both leave the catalog populated. CLI/API/worker startup must also ensure the seed exists on an already migrated database, rather than relying exclusively on a one-time schema migration.
- Keep `cli-reset` focused on collected jobs, sightings, and run history, preserving catalog configuration. Dropping the entire database also deletes discovered targets; the next initialization restores only packaged baseline targets. No historical backup or compatibility system is added.
- Continue keeping migration history and unrelated tables/services intact. Bootstrap errors stop startup with an actionable error rather than allowing a scrape with missing baseline targets.

## Verified discovery

- General-board connectors retain an actual public application URL, when exposed by their response, in `JobPosting.attributes.application_url`; do not infer one from a company name. Extract candidates from that URL and `source_url`, and allow explicit user-supplied supported board URLs through the discovery control. Boards that expose neither URL cannot contribute automatic discoveries. Handle only the five supported ATS providers with strict host and account parsing; do not fetch arbitrary user-supplied hosts or private-network destinations. Redirects must obey the same destination restrictions.
- Persist candidates as disabled and needing review. Deduplicate by provider/account. Do not delay saving valid jobs while verifying company candidates.
- Provide an explicit bounded discovery/verification operation through CLI and web control. Network checks use the existing shared HTTP client, Chrome impersonation, per-domain maximum of three requests, and 1–3 second pacing.
- For initial discovery, enable only when a nonempty captured feed passes the actual parser without model errors, unknown dates, or exposed caps, and employer identity is established from provider metadata or explicit employer evidence. Workday uses a bounded first listing page and at least one dated detail; it must be labeled bounded verification, and totals above the 10,000-job traversal ceiling or facets above the reported total remain pending. This does not certify complete current inventory. Empty feeds, ambiguous identities, partially undated captures, and failed requests remain pending with an explicit reason. Existing enabled targets retain their state on transient errors.
- Track results and reasons per account. Temporary failures must not permanently disable existing verified accounts on a single request. Explicit enable/disable updates are preserved across startup seeding.
- Retain discovered account references in metadata separately from stored jobs; deleting scraped jobs through `cli-reset` must not delete the growing catalog.

## Collection capacity and visibility

- Separate general-board and company-ATS task classes in the shared worker while preserving the existing RunControl, RunStore, TaskTransport, JobSink, and HttpClient ports.
- Source-slot reservation alone is insufficient because worker slots belong to whole runs today. A separate scheduling design must cover queued mixed runs as well as ATS-only runs, stop/retry/redelivery, and configurable concurrency. It must reserve general-board capacity without claiming that a source semaphore prevents run-level blocking. With three source slots, the intended ATS maximum is two; when configured run concurrency is one, execution is sequential and fairness applies at task boundaries without preemption. This scheduling change is a separate stage, not a property delivered by the database catalog stage.
- Preserve overlapping-source support, individual stop controls, retry semantics, and broker/memory parity. No second worker host or distributed rate limiter is introduced.
- Both classes share the existing HTTP client and per-domain safety limits. Capacity reservation does not increase the three-request per-domain ceiling.
- Report company results and catalog health separately from stored job counts. Publication-date ordering for newest postings, with a deterministic tie-breaker, is a separate small UI/API change; preserve existing filters and pagination. Exact date remains visible beneath relative time.

## Validation and delivery

Implement in separately reviewed stages: reset-safe database catalog and injected targets first; bounded discovery and controls second; capacity reservation third. Publication-date ordering can be delivered independently. Each stage must preserve current collection paths and clearly report what is operational. This document approves the overall direction; each independent subsystem receives its own implementation plan, and scheduling must resolve the mixed-run admission design before implementation.

Use the project's minimal permanent testing policy. Keep network/parser validation in bounded manual checks or captured-response checks. Verify initialization on a disposable fresh project database and repeat bootstrap to prove no duplicates or runtime-state overwrites. Verify CLI reset preserves targets, and full recreation restores baseline mappings. Exercise both memory and Redis paths with deterministic local/manual scenarios, including graceful stop, queued recent-board admission, and per-domain limits. Do not reset the user's currently running database merely to test bootstrap.

No dependencies, generalized crawling framework, automatic recurring scheduler, or backup system are required. Keep this design and subsequent implementation uncommitted until explicitly requested.
