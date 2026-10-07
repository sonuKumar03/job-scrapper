# Deployment and operations

## Target layout

- Vercel: frontend, with project root `frontend`, build command `npm run build`, and output directory `dist`.
- Railway: API and one external scraping worker, using the backend Dockerfile's `production` target.
- Separate PostgreSQL and Redis services: use private connectivity where available.

This layout has not been deployed or verified yet. Before exposing scrape controls publicly, add an authentication boundary. `/api/session` issues a request token; it does not authenticate users.

The local `make up` stack remains for development, with source mounts and API reload. It is not a production deployment command.

## Runtime configuration

Supply `DATABASE_URL` to both API and worker. Set `SCRAPE_EXECUTOR=broker` and `SCRAPE_BROKER_URL` on both services. The Redis service must support standard Redis protocol and Streams commands; an HTTP-only key/value API is insufficient. Use durable persistence and a no-eviction policy. Each project database needs a distinct Redis database number or `SCRAPE_BROKER_STREAM`.

The API image starts on `0.0.0.0:8000`; configure the hosting service to route to port 8000. Start the worker with `job-scrapper worker`, give it no public domain, and keep its replica count at one. A database ownership lock rejects a second worker host. Concurrency within that worker defaults to three runs, with 20 unfinished reservations. Overlapping sources are allowed; domain request limits still apply.

Set `API_ALLOWED_HOSTS` and `API_ALLOWED_ORIGINS` explicitly as JSON arrays matching the deployed domains. Avoid wildcards. The frontend can use `VITE_API_URL` pointing to the API, or a Vercel external rewrite for `/api` to keep browser requests on the frontend origin. `VITE_API_URL` is build-time configuration and must never contain credentials.

The backend image includes web, Redis, and Parquet support. Naukri's browser fallback additionally needs the browser extra, Chromium, and OS dependencies; it is not provided by the current image. Inspect per-source results rather than assuming complete coverage.

## Initialization and upgrades

Run these commands against the target database before starting API and worker:

```sh
alembic upgrade head
python -m job_scrapper.companies.bootstrap
```

Assign migration execution to one deployment owner; start the worker after migrations succeed. Seeding is idempotent and preserves existing runtime catalog values. Do not rewrite applied migrations. Finish or stop active runs before changing execution modes or deploying incompatible schema changes.

`job-scrapper reset` clears collected jobs and run history while retaining company configuration and migration history. Full database recreation loses runtime catalog discoveries and edits; initialization restores the packaged baseline. Do not reset unrelated databases.

## Health and recovery

`/health` checks API process liveness. `/ready` checks PostgreSQL and local execution admission with a bounded query. In broker mode it does not certify Redis or external worker availability: monitor worker logs, queued runs, and dispatch delays separately.

Graceful stop saves current batches and retains already committed data. Runtime cleanup allows up to 60 seconds; configure the hosting termination grace period to accommodate that cleanup. The API allows five seconds for HTTP requests to drain before cancellation and runtime shutdown.

Memory-host crash recovery marks unfinished runs interrupted at startup. Broker recovery resumes durable queued/retry work and acknowledges deliveries after committed state. Transient Redis failures back off without discarding accepted work. If database loss invalidates memory-host ownership, restart the API after restoring PostgreSQL.

## Exports and verification

Use `job-scrapper export --format jsonl --days 7 --output /app/data/jobs.jsonl`, or `--format parquet`. Container filesystems are ephemeral unless persistence is configured: download exports before replacement, or provide durable storage. Successful exports replace their destination atomically. Keep datasets and credentials out of source control and public reports.

Run `make check`, `make web-build`, `uv build`, and the backend production image build before release. Verify migrations, API/worker connectivity, host/origin rejection, authentication, graceful stop, dependency outage recovery, and frontend interactions in an isolated deployment before claiming public readiness.
