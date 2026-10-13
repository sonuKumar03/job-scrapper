# 🕷️ Job Scrapper

> High-volume job scraping engine — 16 sources, 3-layer deduplication, ML-ready exports.

Collects ~10k jobs/day from job boards and company ATS providers, deduplicates across sources, and exports clean datasets for machine learning classification. Ships with a React dashboard for browsing and managing scrapes.

---

## ⚡ Tech Stack

| | Technology |
| :--- | :--- |
| **Language** | Python 3.11+, `uv` |
| **Database** | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| **HTTP** | `curl_cffi` — Chrome 120 TLS impersonation |
| **Frontend** | React 19 · Vite · Tailwind · TanStack Query |
| **CLI** | `typer` · `rich` |

---

## 🏗️ How It Works

```
Job Boards ──→ Connectors ──→ JobPosting ──→ Dedup Engine ──→ PostgreSQL ──→ JSONL / Parquet
```

**16 Sources** — Himalayas · Jobicy · Arbeitnow · RemoteOK · LinkedIn · Naukri · HackerNews · We Work Remotely · Built In · Hirist · Instahyre + ATS providers (Greenhouse · Lever · Ashby · Workday · Workable) covering 608 company targets.

**3-Layer Dedup** — Canonical signature (SHA-256) → SimHash near-duplicate detection (Hamming ≤ 3) → cross-source attribute enrichment.

---

## 🚀 Quickstart

> Prerequisites: Docker with Compose v2 and Make.

```sh
make up              # Full stack → API :8000, Dashboard :3000
make cli-scrape      # Scrape all sources (last 7 days)
make cli-export      # Export to JSONL
make cli-status      # Show stored job counts
make down            # Stop services
```

### Native Development

```sh
make setup           # Dependencies, PostgreSQL, migration & seed
make api             # API → http://127.0.0.1:8000
make web             # Dashboard → http://localhost:3000
make check           # Lint + tests
```

### Common Options

```sh
make cli-scrape source=jobicy days=1                    # Single source
make cli-scrape source=workable days=1                  # ATS provider
make cli-export format=parquet                          # Parquet export
make cli-export export_args='--work-arrangement remote' # Filtered export
make cli-reset                                          # Clear scraped data
```

---

## 📊 Dashboard

Browse jobs with search, filters (source · company · work arrangement · experience), full descriptions, and scrape run management with per-source stop controls.

> API docs → http://127.0.0.1:8000/docs

---

## 📁 Project Structure

```
job-scrapper/
├─ frontend/                # React dashboard (Vite + Tailwind)
├─ src/job_scrapper/
│  ├─ connectors/           # 16 source connectors
│  ├─ pipeline/             # Dedup · date parsing · attribute normalization
│  ├─ storage/              # JobSink protocol · PostgreSQL implementation
│  ├─ execution/            # Run lifecycle · memory/broker transports
│  ├─ companies/            # Company catalog & ATS targets
│  ├─ exporters/            # JSONL and Parquet batch export
│  ├─ web.py                # FastAPI REST API
│  └─ cli.py                # Typer CLI
├─ migrations/              # Alembic revisions
└─ tests/
```

---

## 📚 Docs

- **[Operations](docs/operations.md)** — deployment, configuration, health checks
- **[Contributing](CONTRIBUTING.md)** — setup, architecture boundaries, checks
- **[Security](SECURITY.md)** — deployment boundary and reporting

---

## 📄 License

[MIT](LICENSE)
