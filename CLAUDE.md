# CLAUDE.md

Quick reference and developer commands for `job-scrapper`.

## Priority & Disposable Scraped Data

- The main goal is reliable, complete, and efficient scraping at scale (~10k jobs/day). Prioritize improving the scraping workflow and throughput.
- Existing scraped data is disposable. Agents may delete or reset this project's scraped jobs, sightings, scrape-run records, and generated dataset exports when required for development, fixes, or validation, without asking for additional confirmation.
- Backups, historical data recovery, and compatibility with old scraped records are not required. Scope resets to this project's scraped data and preserve unrelated databases, tables, files, and services.

---

### Developer Commands
```bash
rtk make setup
rtk make up
rtk make down
rtk make scrape
rtk make export
rtk make parquet
rtk make status
rtk make reset
rtk make test
```

Defaults: scrape all sources from the last seven days; export the last seven days. Use `rtk make help` for other targets. For a specific source, use `rtk make scrape source=himalayas`.

For live development checks, use `rtk make scrape source=jobicy days=1` (or the source being checked). Keep diagnostic page counts bounded for feeds that still require full traversal.

Company ATS connectors (`greenhouse`, `lever`, `ashby`, `workable`, `workday`) collect all currently listed jobs regardless of `days`. Their results are reported per company account. Use a specific source for a bounded check, for example `rtk make scrape source=workable days=1`; `days=1` does not limit the number of active jobs on that company board.

`rtk make reset` deletes jobs, sightings, and scrape-run records from the configured database. Stop scrapers before resetting. Schema and migration history are preserved.

---

## 📐 Architecture & Conventions

1. **Decoupled Sinks**: Connectors must only interact with `JobSink` and yield `JobPosting` objects. Never import database models or engines inside `connectors/`.
2. **Dynamic Attributes**: Store ML classification tags inside `JobPosting.attributes` (`dict[str, Any]`), mapped to PostgreSQL `JSONB`.
3. **Anti-Bot & Rate Limits**:
   - Use `ResilientHttpClient` (`curl_cffi` impersonating `chrome120`).
   - Enforce 1–3s jitter and max 3 concurrent requests per domain.
4. **Command Execution**: Always prefix terminal commands with `rtk ` (e.g. `rtk uv run ...`).
