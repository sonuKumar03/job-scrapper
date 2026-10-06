"""Loopback dashboard API. Optional web dependencies are imported only here."""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from starlette.middleware.trustedhost import TrustedHostMiddleware

from job_scrapper.connectors.registry import list_connectors
from job_scrapper.runner import ScrapeBusyError, execution_snapshot, reconcile_executions, run_scrape
from job_scrapper.storage.postgres.models import JobModel, ScrapeExecutionModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
Page = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


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
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = DatabaseSessionManager()
        app.state.manager = manager
        app.state.task = None
        app.state.token = secrets.token_urlsafe(32)
        try:
            await reconcile_executions(manager)
            yield
        finally:
            task = app.state.task
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await manager.close()

    app = FastAPI(title="Job Scrapper", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if origin is not None and origin != expected:
                return JSONResponse({"detail": "Requests must come from this dashboard."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site requests are not allowed."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return JSONResponse({"detail": "Send application/json."}, status_code=415)
            token = request.headers.get("x-scrape-token", "")
            if not secrets.compare_digest(token.encode(), app.state.token.encode()):
                return JSONResponse({"detail": "Refresh this page before starting a scrape."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logger.error("Dashboard database request failed: %s", type(error).__name__)
        return JSONResponse({"detail": "Database unavailable. Check PostgreSQL and run make migrate."}, status_code=503)

    @app.get("/api/session")
    async def session_info():
        return {"token": app.state.token, "sources": list_connectors()}

    @app.get("/api/filters")
    async def filters():
        async with app.state.manager.session() as session:
            sources = (await session.scalars(select(JobModel.source).distinct().order_by(JobModel.source))).all()
            companies = (await session.scalars(select(JobModel.company_name).distinct().order_by(JobModel.company_name))).all()
        return {"sources": sources, "companies": companies}

    @app.get("/api/jobs")
    async def jobs(
        page: Page = 1, page_size: PageSize = 25,
        q: Annotated[str, Query(max_length=200)] = "",
        source: Annotated[str, Query(max_length=64)] = "",
        company: Annotated[str, Query(max_length=500)] = "",
    ):
        if page_size not in {25, 50, 100}:
            raise HTTPException(422, "Rows per page must be 25, 50, or 100.")
        predicates = []
        if q.strip():
            literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            predicates.append(or_(JobModel.title.ilike(f"%{literal}%", escape="\\"),
                                  JobModel.company_name.ilike(f"%{literal}%", escape="\\")))
        if source:
            predicates.append(JobModel.source == source)
        if company:
            predicates.append(JobModel.company_name == company)
        statement = select(JobModel.id, JobModel.title, JobModel.company_name,
                           JobModel.source, JobModel.posted_at, JobModel.scraped_at).where(*predicates)
        async with app.state.manager.session() as session:
            total = await session.scalar(select(func.count()).select_from(JobModel).where(*predicates))
            result = await session.execute(statement.order_by(JobModel.scraped_at.desc(), JobModel.id.desc())
                                           .offset((page - 1) * page_size).limit(page_size))
            items = [dict(row) for row in result.mappings()]
        return jsonable_encoder({"items": items, "total": total, "page": page, "page_size": page_size})

    @app.get("/api/jobs/{job_id}")
    async def job_detail(job_id: UUID):
        async with app.state.manager.session() as session:
            job = await session.scalar(select(JobModel).where(JobModel.id == job_id)
                                       .options(selectinload(JobModel.sightings)))
            if job is None:
                raise HTTPException(404, "Job not found. It may have been removed by a reset.")
            data = columns(job)
            data["sightings"] = [columns(sighting) for sighting in sorted(job.sightings, key=lambda s: (s.source, s.source_job_id))]
        return jsonable_encoder(data)

    @app.get("/api/runs")
    async def runs(page: Page = 1, page_size: PageSize = 25):
        if page_size not in {25, 50, 100}:
            raise HTTPException(422, "Rows per page must be 25, 50, or 100.")
        async with app.state.manager.session() as session:
            total = await session.scalar(select(func.count()).select_from(ScrapeExecutionModel))
            rows = (await session.scalars(select(ScrapeExecutionModel)
                    .order_by(ScrapeExecutionModel.started_at.desc(), ScrapeExecutionModel.id.desc())
                    .offset((page - 1) * page_size).limit(page_size))).all()
            # Account results are omitted from summary responses.
            items = [{key: value for key, value in execution_snapshot(row).items() if key != "results"} for row in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: UUID):
        async with app.state.manager.session() as session:
            row = await session.get(ScrapeExecutionModel, run_id)
            if row is None:
                raise HTTPException(404, "Scrape run not found.")
            return execution_snapshot(row)

    @app.post("/api/runs", status_code=202)
    async def start_run(body: StartScrape):
        if app.state.task and not app.state.task.done():
            raise HTTPException(409, "A scrape is already running. View its status below.")
        started = asyncio.get_running_loop().create_future()

        async def receive(snapshot: dict[str, Any]) -> None:
            if not started.done():
                started.set_result(snapshot)

        async def background() -> None:
            try:
                await run_scrape(app.state.manager, body.sources, body.days, on_update=receive)
            except Exception as error:
                if not started.done():
                    started.set_exception(error)
                else:
                    logger.error("Background scrape stopped: %s", type(error).__name__)
            except asyncio.CancelledError:
                if not started.done():
                    started.cancel()
                raise

        # Consume startup exceptions even if the HTTP client disconnects.
        started.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
        app.state.task = asyncio.create_task(background())
        try:
            snapshot = await asyncio.shield(started)
        except ScrapeBusyError as error:
            raise HTTPException(409, str(error)) from error
        return {"id": snapshot["id"], "status": "running"}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
