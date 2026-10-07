# Contributing

Use Python 3.11+, uv, Make, and Docker with Compose v2. Native frontend work also needs Node 22 and npm. RTK is an agent tool required by AGENTS.md; human contributors do not need it to run Make commands.

## Setup

```sh
make setup
make check
```

Setup installs frozen Python dependencies, copies `.env.example` when needed, starts PostgreSQL, migrates its schema, and inserts missing company seed records. It does not start the API or scraper. `uv sync --frozen --extra web` installs the standard development group; `--extra broker`, `--extra export`, and `--extra browser` add optional capabilities.

For the full development stack, use `make up` and open http://localhost:3000. Use `make up executor=broker` for Redis and one worker. Use `make down` before changing execution modes.

For native work, keep the container API/worker stopped:

```sh
docker compose up -d --wait db
make migrate
make api
# In another terminal:
make web
```

The API listens on 127.0.0.1:8000; Vite uses port 3000. Do not run the native and container dashboard on the same ports. In memory mode, only one CLI/API process can own the worker against a database.

## Checks

```sh
make check                     # Narrow correctness lint + unit tests
make web-build                 # Locked frontend install and production build
uv build                       # Python wheel and source distribution
```

CI checks Python 3.11 and 3.13, the frontend build, packaged seed, and backend production image. It does not scrape live job boards. Hosted CI only runs after pushing to a configured GitHub repository.

## Architecture and changes

- Connectors extract data into `JobPosting` and call the `JobSink` port. They never access PostgreSQL or company repositories.
- Resolve company targets through the existing repository at task start, and pass immutable snapshots into ATS connectors. `company_seed.json` initializes missing records; it is not runtime connector configuration.
- Add classification features to `attributes`, not individual database columns.
- Preserve per-domain maximum three requests, 1–3 second pacing, Chrome impersonation, and pre-fetch identity deduplication. Browser fallback needs the browser extra and installed Chromium.
- Preserve explicit failure/incomplete-coverage results. An empty failed feed is not a successful zero-job scrape.
- Use additive Alembic migrations; do not rewrite previously applied revisions. `make migrate` also performs idempotent catalog initialization.
- Keep changes focused. Avoid speculative frameworks, dependencies, and unrelated formatting.

Permanent tests stay minimal: domain contracts, pure pipeline transforms, and InMemoryJobSink behavior. Use captured responses for parser checks and isolated local resources for storage/execution acceptance. Do not add live-network CI tests or heavy mock frameworks. Manual live diagnostics select only the relevant source, a one-day window, and a bounded page count when necessary.

`make cli-reset` removes scraped jobs, sightings, and execution history, retaining company configuration and schema. Stop scrapers before resetting. Never operate on someone else's database or unrelated tables. See [operations](docs/operations.md) for runtime recovery and production verification.

## Pull requests

Explain the concrete before/after behavior, list the checks you ran, and describe configuration or migration changes. Include sanitized reproduction details. Do not include `.env` files, credentials, generated datasets, or captured personal data. License contributions under the repository's [MIT license](LICENSE).

Security reports follow [SECURITY.md](SECURITY.md); do not disclose sensitive vulnerabilities through a public issue.
