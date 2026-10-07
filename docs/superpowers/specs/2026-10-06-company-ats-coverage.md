# Company ATS Coverage Design

> Historical runtime design: as of 2026-10-07, PostgreSQL supplies company targets. The packaged directory and provider defaults have moved to initialization-only `company_seed.json`; see the dynamic-company coverage design. Verification snapshots below remain historical evidence, not current inventory guarantees.

## Goal

Collect every currently listed posting from companies in the moreThanFAANGM directory and additional verified employers when their public job boards are supported, regardless of posting age, and make coverage gaps visible so more companies can be added through shared ATS adapters.

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

## Coverage expansion on 2026-10-07

Enabled 48 additional directory companies, bringing supported catalog coverage to **100 of 482**. Existing supported records and provider defaults remain enabled. This expands the existing adapters without adding dependencies or changing request limits.

| Provider | Added | Supported catalog total |
| --- | ---: | ---: |
| Greenhouse | 26 | 42 |
| Workday | 15 | 40 |
| Lever | 6 | 8 |
| Ashby | 1 | 9 |
| Workable | 0 | 1 |

New companies:

- Greenhouse: AQR, Arcesium, Careem, Coupang, Dashlane, Dialpad, DigitalOcean, Discord, Doximity, Epic Games, GoDaddy, Grafana, Groupon, HackerRank, InMobi, LogicMonitor, Ocrolus, PubMatic, Rockstar Games, Rubrik, Roku, Sigmoid, Sureify, ThoughtWorks, Upwork, WorldQuant.
- Workday: Adobe, Applied Materials, Athena Health, BlackRock, Blue Origin, Broadcom, Equinix, FactSet, HP, Intel, Mastercard, PayPal, Salesforce, Wells Fargo, Yahoo.
- Lever: Appen, Bazaarvoice, FamPay, Meesho, Turvo, Zeta.
- Ashby: Atlan.

Verification:

- Checked public listing responses using the shared paced HTTP client. Greenhouse board metadata confirmed employer names. Account aliases such as `digitalocean98`, `ocrolusinc`, and `arcesiumllc` are retained explicitly rather than inferred from company names.
- Checked Workday response totals and facets for exposed caps, plus one description and publication date from each newly enabled board. Workday validation was bounded to the first listing page and one detail; it does not certify retrieval of every current posting.
- Passed captured-response checks through the actual connectors and `InMemoryJobSink` for all 48 enabled additions, including canonical model validation, account-scoped IDs, and repeat-ingestion deduplication. Lever captured checks used one listing; they are parser checks, not complete feed counts.
- Live one-day smoke checks saved 6 Ocrolus, 16 Careem, 3 Turvo, and 6 Atlan postings in memory, with no errors or truncation. Turvo was bounded to two pages. PostgreSQL was not modified.
- All 13 existing project tests passed. No automated live-network tests were added.

Kept unresolved:

- NVIDIA: reported 2,000 listings while a facet reported 2,655, indicating capped results.
- Tower Research Capital: 2 of 93 listings lacked usable publication dates in the captured response.
- Gartner: the sampled detail had a future UTC publication date and failed canonical model validation.
- Failed candidate account URLs remain unresolved; a guessed account returning 404/422 is not evidence that the company's entire careers site is unavailable.

The catalog still contains all 482 original companies and their original source URLs. The remaining 382 entries are unresolved or unsupported. These checks establish usable provider mappings at verification time; availability and complete inventory remain observable per-run outcomes.

## Expansion to 200 on 2026-10-07

Enabled another 100 company boards using existing adapters. The catalog now contains **570 companies, with 200 supported**: 112 of the original 482 directory companies and 88 additional employers. All original source URLs and the previous 100 supported records are preserved. The remaining 370 directory entries remain unresolved or unsupported.

| Provider | Added in this expansion | Supported catalog total |
| --- | ---: | ---: |
| Greenhouse | 35 | 77 |
| Ashby | 53 | 62 |
| Workday | 11 | 51 |
| Workable | 1 | 2 |
| Lever | 0 | 8 |

New directory mappings include ASML, BMC software, Deutsche Bank, eBay, Fidelity investments, fiserv, GE Healthcare, Phillips (the directory's spelling for Philips), Samsung, Shell, Sony, and Apna. Additional employers include Cockroach Labs, ClickHouse, Pinecone, Neo4j, Cohere, WorkOS, Adyen, Cerebras, Roblox, and Pinterest. Each catalog record retains its verified provider account and board URL.

Verification:

- Verified nonempty public listing responses with the existing paced HTTP client. Greenhouse board metadata and Ashby account URLs/employer descriptions were checked against the expected employer identity.
- Passed captured-response checks through actual connectors and `InMemoryJobSink` for all 100 additions, including canonical model validation, account-scoped identifiers, and repeat-ingestion deduplication. Greenhouse and Ashby checks used their complete captured feeds; Workable parsed 111 Apna postings.
- Workday checks inspected listing totals and facets plus the first listing page and one dated detail per board. These bounded checks establish usable mappings, not exhaustive inventory retrieval.
- Live checks with `max_days=1` saved 18 Cockroach Labs, 3 Knock, and 111 Apna postings in memory, with no errors or truncation. Company ATS feeds intentionally include older open jobs regardless of this day setting. PostgreSQL was not modified.
- Rejected Lowe's because its 21,164 reported postings exceed the existing 10,000-job traversal ceiling. Rejected the candidate Intercom account because its board metadata identifies Fin. Neither is enabled by this expansion.
- All 13 existing project tests passed. No dependencies, connector implementations, permanent network tests, or database records were changed.

Supported means a verified usable mapping at this snapshot. Per-run errors, missing publication dates, and traversal limits still determine actual collection completeness.
