"""FastAPI REST API for Job Scrapper."""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from starlette.middleware.trustedhost import TrustedHostMiddleware

from job_scrapper.connectors.registry import list_connectors
from job_scrapper.config import get_settings
from job_scrapper.execution.bootstrap import execution_runtime
from job_scrapper.execution.contracts import RunConflict, StartScrapeCommand
from job_scrapper.storage.postgres.models import JobModel, ScrapeExecutionModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.job_filters import JobFilters, job_predicates
from job_scrapper.storage.postgres.models import WORK_ARRANGEMENT, EMPLOYMENT_TYPE, EXPERIENCE_MIN, EXPERIENCE_MAX

logger = logging.getLogger(__name__)

Page = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def read_job_filters(q: str = '', source: str = '', company: str = '',
                     work_arrangement: str = '', employment_type: str = '',
                     experience_min: float | None = None, experience_max: float | None = None) -> JobFilters:
    try:
        return JobFilters(q=q, source=source, company=company, work_arrangement=work_arrangement,
                          employment_type=employment_type, experience_min=experience_min, experience_max=experience_max)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


class StartScrape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(min_length=1, max_length=100)
    days: int = Field(default=1, ge=1, le=365, strict=True)

    @field_validator("sources")
    @classmethod
    def known_sources(cls, value: list[str]) -> list[str]:
        if set(value) - set(list_connectors()):
            raise ValueError("Select registered scraper sources.")
        return list(dict.fromkeys(value))


def columns(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def create_app() -> FastAPI:
    settings = get_settings()
    database_probe: asyncio.Task | None = None
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = DatabaseSessionManager()
        app.state.manager = manager
        app.state.token = secrets.token_urlsafe(32)
        try:
            async with execution_runtime(manager) as control:
                app.state.control = control
                yield
        finally:
            if database_probe is not None:
                database_probe.cancel()
                await asyncio.gather(database_probe, return_exceptions=True)
            await manager.close()

    app = FastAPI(
        title="Job Scrapper API",
        description="Clean REST API for browsing scraped job postings, deduplication metadata, and triggering background scrape runs.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Enable CORS for decoupled frontends (Vite dev server, standalone react app, etc.)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Scrape-Token"],
    )

    @app.middleware("http")
    async def security_and_token_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get('origin')
            if origin is not None and origin not in settings.api_allowed_origins:
                return JSONResponse({'detail': 'Request origin is not allowed.'}, status_code=403)
            content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                return JSONResponse({"detail": "Send application/json."}, status_code=415)
            token = request.headers.get("x-scrape-token", "")
            if not token or not secrets.compare_digest(token.encode(), app.state.token.encode()):
                return JSONResponse({"detail": "Valid X-Scrape-Token header required. Fetch from /api/session first."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.api_allowed_hosts, www_redirect=False)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logger.error("Dashboard database request failed: %s", type(error).__name__)
        return JSONResponse({"detail": "Database unavailable. Check PostgreSQL and run make migrate."}, status_code=503)

    @app.exception_handler(RunConflict)
    async def execution_conflict(request: Request, error: RunConflict):
        return JSONResponse({'detail': str(error)}, status_code=409)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get('/ready')
    async def ready():
        nonlocal database_probe
        components = {'database': 'ok', 'execution': 'ok'}

        async def probe_database():
            async with app.state.manager.session() as session:
                await session.execute(select(1))

        # Driver cancellation can wait on an unresponsive server. Share one
        # in-flight probe instead of blocking responses or piling up queries.
        if database_probe is not None and database_probe.done():
            try:
                database_probe.result()
            except (SQLAlchemyError, TimeoutError):
                pass
            database_probe = None
        if database_probe is None:
            database_probe = asyncio.create_task(probe_database())
        probe = database_probe
        done, _ = await asyncio.wait((probe,), timeout=2)
        try:
            if not done:
                raise TimeoutError
            probe.result()
        except (SQLAlchemyError, TimeoutError):
            components['database'] = 'unavailable'
        finally:
            if done and database_probe is probe:
                database_probe = None
        try:
            app.state.control.check_health()
        except RunConflict:
            components['execution'] = 'unavailable'
        available = all(value == 'ok' for value in components.values())
        return JSONResponse({'status': 'ok' if available else 'unavailable', 'components': components},
                            status_code=200 if available else 503)

    @app.get("/api/session")
    async def session_info():
        return {"token": app.state.token, "sources": list_connectors()}

    @app.get("/api/filters")
    async def filters(filters: Annotated[JobFilters, Depends(read_job_filters)]):
        facets = {}
        async with app.state.manager.session() as session:
            for field, column in (('source', JobModel.source), ('company', JobModel.company_name),
                                  ('work_arrangement', WORK_ARRANGEMENT), ('employment_type', EMPLOYMENT_TYPE)):
                rows = await session.execute(select(column, func.count()).select_from(JobModel)
                    .where(*job_predicates(filters, exclude=field)).group_by(column).order_by(column))
                facets[field] = [{'value': value, 'count': count} for value, count in rows]
            bounds = (await session.execute(select(func.min(EXPERIENCE_MIN), func.max(EXPERIENCE_MAX))
                .select_from(JobModel).where(*job_predicates(filters, exclude='experience')))).one()
        return {'sources': [r['value'] for r in facets['source']],
                'companies': [r['value'] for r in facets['company']], 'facets': facets,
                'experience': {'min': bounds[0], 'max': bounds[1]}}

    @app.get("/api/jobs")
    async def jobs(
        page: Page = 1,
        page_size: PageSize = 25,
        filters: Annotated[JobFilters, Depends(read_job_filters)] = None,
    ):
        if page_size not in {25, 50, 100}:
            raise HTTPException(422, "Rows per page must be 25, 50, or 100.")
        predicates = job_predicates(filters)
        statement = select(
            JobModel.id,
            JobModel.title,
            JobModel.company_name,
            JobModel.source,
            JobModel.source_url,
            JobModel.posted_at,
            JobModel.scraped_at,
            JobModel.attributes,
        ).where(*predicates)
        async with app.state.manager.session() as session:
            total = await session.scalar(select(func.count()).select_from(JobModel).where(*predicates))
            result = await session.execute(
                statement.order_by(JobModel.scraped_at.desc(), JobModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = [dict(row) for row in result.mappings()]
        return jsonable_encoder({"items": items, "total": total, "page": page, "page_size": page_size})

    @app.get("/api/jobs/count")
    async def job_count():
        async with app.state.manager.session() as session:
            total = await session.scalar(select(func.count()).select_from(JobModel))
        return {"total": total or 0}

    @app.get("/api/jobs/{job_id}")
    async def job_detail(job_id: UUID):
        async with app.state.manager.session() as session:
            job = await session.scalar(
                select(JobModel).where(JobModel.id == job_id).options(selectinload(JobModel.sightings))
            )
            if job is None:
                raise HTTPException(404, "Job not found. It may have been removed by a reset.")
            data = columns(job)
            data["sightings"] = [
                columns(sighting) for sighting in sorted(job.sightings, key=lambda s: (s.source, s.source_job_id))
            ]
        return jsonable_encoder(data)

    @app.get("/api/runs")
    async def runs(page: Page = 1, page_size: PageSize = 25):
        if page_size not in {25, 50, 100}:
            raise HTTPException(422, "Rows per page must be 25, 50, or 100.")
        async with app.state.manager.session() as session:
            total = await session.scalar(select(func.count()).select_from(ScrapeExecutionModel))
            rows = (
                await session.scalars(
                    select(ScrapeExecutionModel)
                    .order_by(ScrapeExecutionModel.queued_at.desc(), ScrapeExecutionModel.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            run_ids = [row.id for row in rows]
        items = []
        for run_id in run_ids:
            run = await app.state.control.get(run_id)
            if run is not None:
                items.append(run.model_dump(mode='json', exclude={'results'}))
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @app.get('/api/runs/active')
    async def active_runs():
        control = app.state.control
        return {'items': [run.model_dump(mode='json') for run in await control.list_active()],
                'capacity': control.capacity.model_dump()}

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: UUID):
        run = await app.state.control.get(run_id)
        if run is None:
            raise HTTPException(404, 'Scrape run not found.')
        return run.model_dump(mode='json')

    @app.post("/api/runs/{run_id}/stop", status_code=202)
    async def stop_run(run_id: UUID):
        run = await app.state.control.request_stop(run_id)
        if run is None:
            raise HTTPException(409, "This scrape is no longer active. Refresh run history.")
        return {'id': str(run.id), 'status': run.status}

    @app.post("/api/runs", status_code=202)
    async def start_run(body: StartScrape):
        run = await app.state.control.submit(StartScrapeCommand(sources=tuple(body.sources), days=body.days))
        return {'id': str(run.id), 'status': run.status}

    return app
