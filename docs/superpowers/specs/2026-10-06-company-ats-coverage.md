# Company ATS Coverage Design

## Goal

Collect every currently listed posting from companies in the moreThanFAANGM directory when its public job board is supported, regardless of posting age, and make coverage gaps visible so more companies can be added through shared ATS adapters.

## Context and constraints

- The directory has 483 entries and 482 distinct company names; Ninjacart is duplicated.
- Its URLs include direct ATS boards, general career pages, stale links, blocked pages, and company homepages.
- A reachable careers page is not evidence that a machine-readable job listing is available.
- Existing connectors for Greenhouse, Lever, and Ashby use fixed company lists.
- Keep those existing targets enabled. The new directory catalog is additive and must not silently reduce current connector coverage.
- `JobPosting.posted_at` is required by the domain model and database. Do not invent a posting date when a source does not provide one; report and skip those listings in this phase.
- Connectors continue to use `JobPosting`, `JobSink`, the shared paced HTTP client, and the existing per-domain request limits.
- Do not add dependencies, generic site crawling, stealth browser automation, or historical-data compatibility work.
- Keep all changes uncommitted until the user explicitly requests commits.

## Design

### Company catalog

Add a versioned catalog containing the 482 distinct companies and their original directory URLs. Each record has a stable company key, display name, source URL, detected platform, provider account/board identifier when known, and a verification state. Use states that distinguish supported, needs review, unsupported, unavailable, and blocked sources. The catalog is configuration, not generated scraped-job data, and must ship with the package.

An optional `board_url` records a verified ATS board reached from the directory page. Workday uses this URL for the ATS host while `source_url` retains the original directory URL.

Initially classify direct mappings for the existing Greenhouse, Lever, and Ashby adapters and the newly validated Workable and Workday boards. Merge supported catalog accounts with existing provider defaults, deduplicated by account key. Include Zoho Recruit as a candidate only after confirming a stable public listing interface. Keep all other companies in the catalog as unresolved until their provider and listing interface are established.

### Platform adapters

Reuse the current ATS connectors and make their target accounts configurable from the catalog. Add shared adapters for Workable and Workday, plus Zoho Recruit if its public listing interface is confirmed. One connector handles multiple company accounts for its platform; do not create one connector per company.

Use provider plus account key when constructing `source_job_id`, so equal job IDs on different company boards cannot collide under the database uniqueness constraint. Preserve the employer name and provider account in the normalized posting and its attributes.

### Scraping behavior

- Fetch the complete current listing set from each enabled company ATS board; do not apply `--days` to these company feeds.
- Existing general job-board connectors retain their current `--days` behavior.
- Use listing APIs where available. Check the sink for known IDs before fetching an expensive detail page; save through the existing sink in batches.
- Respect the shared HTTP client's 1–3 second per-domain jitter, maximum three concurrent requests per domain, and Chrome 120 TLS profile.
- A company with no postings is a successful empty result only when the board response is valid and complete. Network, access, and parse failures remain errors; they never count as coverage.
- Workday responses whose facet counts exceed the reported listing total are capped searches. Report them as incomplete and keep these company boards unresolved until searches can be partitioned to retrieve all postings.
- Keep undated postings out of storage in this phase and report them as skipped/errors rather than fabricating `posted_at` values. This is a known coverage limit to revisit if a supported source omits posting dates.

### Reporting and operation

The scrape summary identifies results by platform and company account, including found, inserted, skipped, and failed counts. `source=all` includes registered company ATS connectors; specific providers remain selectable through the existing `--source` option. No new scheduler or database tables are introduced in this phase.

## Out of scope

- Scraping arbitrary career-page HTML for all 482 companies.
- Bypassing CAPTCHAs, access controls, or login requirements.
- Marking stored jobs closed when they disappear from a later listing snapshot.
- Changing export date-window behavior or making `posted_at` nullable.
- Claiming full company coverage while a source is unresolved or its board fetch fails.

## Acceptance criteria

1. The packaged catalog represents all 482 distinct directory companies, preserves each selected original URL, and records a verification state.
2. Every enabled catalog company maps to a supported provider adapter and has a provider account identifier; existing provider defaults remain enabled.
3. Company ATS adapters collect older active listings without the `--days` cutoff while other connectors retain existing behavior.
4. Job identifiers are namespaced by provider account, and all saved jobs flow through `JobPosting` and `JobSink`.
5. A valid empty board is distinguishable from blocked, failed, or malformed responses in scrape results.
6. Unsupported and inaccessible companies remain visible as unresolved rather than being silently treated as covered.
7. The implementation uses existing dependencies and request-pacing rules.

## Known limitation

This phase makes coverage explicit and adds shared support for validated ATS platforms; it does not make every one of the 482 company pages scrapeable. Companies on unsupported or inaccessible systems remain unresolved until a public listing source or compliant adapter is identified.

## Coverage verification on 2026-10-06

- Inspected 443 unresolved public company pages, excluding links to general job boards and social sites. 82 page requests failed or exceeded the diagnostic timeout; these entries remain unresolved.
- Checked 48 discovered accounts using public listing responses. Workday checks included one detail response with a description and publication date per nonempty board.
- Enabled 41 additional companies through the existing adapters: 24 Workday, 9 Greenhouse, 6 Ashby, and 2 Lever. Supported catalog coverage is now 52 of 482 companies; this count includes valid empty boards.
- Bounded in-memory checks with `max_days=1` saved 6 Affinidi, 5 Contra, 19 Mindtickle, and 32 BrowserStack postings without errors or truncation. Lever was limited to one page and BrowserStack to two pages. The Accenture cap check reported incomplete coverage and saved no jobs. These checks did not modify PostgreSQL.
- Directi and Dream Sports Lever feeds returned HTTP 404, and the former IHS Markit Workday feed returned HTTP 422. Their catalog entries are unavailable.
- Kept NCR and Nike unresolved because their pages link to several career boards. Kept Twitter, Juniper, and Hotstar unresolved where links led to a different employer's board.
- Four large Workday boards returned 2,000 listings despite higher facet counts:

| Company | Reported total | Largest observed facet count |
| --- | ---: | ---: |
| Accenture | 2,000 | 42,175 |
| Airbus | 2,000 | 2,937 |
| Citi | 2,000 | 4,059 |
| Target | 2,000 | 14,131 |

These four boards retain `needs_review` status. Counts are verification snapshots, not current job inventory guarantees.
