"""Typer CLI interface for Job Scrapper."""

import asyncio
import signal
from uuid import UUID
from collections import Counter
from importlib.util import find_spec
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select, text
import typer
from job_scrapper.connectors.registry import list_connectors
from job_scrapper.connectors.company_sources import load_company_sources
from job_scrapper.exporters.jsonl import export_jobs_to_jsonl
from job_scrapper.exporters.parquet import export_jobs_to_parquet
from job_scrapper.storage.postgres.models import JobModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.sink import PostgresJobSink
from job_scrapper.runner import run_scrape, scrape_lock, request_scrape_stop, ScrapeBusyError

app = typer.Typer(help="High-volume job scraper and ML dataset generator.")
console = Console()


async def _run_scrape(sources: list[str], days: int, include_catalog_status: bool = False) -> bool:
    session_manager = DatabaseSessionManager()
    table = Table(title=f"Scrape Results (general-board cutoff: Last {days} Days)")
    table.add_column("Source", style="cyan")
    table.add_column("Found", justify="right")
    table.add_column("New Inserted", justify="right", style="green")
    table.add_column("Skipped / Duplicate", justify="right", style="dim")
    table.add_column("Errors", style="red")
    table.add_column("Truncated", style="yellow")
    async def show_started(snapshot: dict) -> None:
        for name, result in snapshot["results"].items():
            if result["status"] == "running" and name not in started:
                started.add(name)
                console.print(f"[bold blue]Scraping {name}...[/bold blue]")

    started: set[str] = set()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def stop_after_batch() -> None:
        if not stop_event.is_set():
            console.print("[yellow]Stopping after the current batch is saved...[/yellow]")
            stop_event.set()

    for sig in previous_handlers:
        loop.add_signal_handler(sig, stop_after_batch)

    try:
        execution = await run_scrape(session_manager, sources, days, on_update=show_started, stop_event=stop_event)
        if execution["status"] == "stopped":
            console.print("[yellow]Scrape stopped gracefully. Saved jobs were preserved.[/yellow]")
        results = execution["results"].items()
        failed = execution["status"] == "stopped"
        for source_name, stats in results:
            if "found" not in stats:
                failed = True
                table.add_row(source_name, "—", "—", "—", "; ".join(stats.get("errors", [])), "yes")
                continue
            rows = stats.get("accounts")
            if rows:
                for account, account_stats in rows.items():
                    errors = "; ".join(account_stats["errors"])
                    table.add_row(
                        f"{source_name}/{account}", str(account_stats["found"]),
                        str(account_stats["inserted"]), str(account_stats["skipped"]),
                        errors, "yes" if account_stats["truncated"] else "no",
                    )
            else:
                table.add_row(
                    source_name, str(stats["found"]), str(stats["inserted"]),
                    str(stats["skipped"]), "; ".join(stats["errors"]),
                    "yes" if stats["truncated"] else "no",
                )
            failed |= bool(stats["errors"] or stats["truncated"])

        console.print(table)
        if include_catalog_status:
            totals = Counter(source.status for source in load_company_sources())
            console.print("Company catalog: " + ", ".join(
                f"{status}={totals[status]}" for status in
                ("supported", "needs_review", "unavailable", "blocked", "unsupported")
            ))
        total_jobs = await PostgresJobSink(session_manager).count()
        console.print(f"\n[bold green]Total jobs stored in database: {total_jobs}[/bold green]")
    except ScrapeBusyError as error:
        console.print(f"[red]{error}[/red]")
        return True
    finally:
        for sig, previous in previous_handlers.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, previous)
        await session_manager.close()
    return failed


@app.command()
def scrape(
    source: str = typer.Option(
        "all", "--source", "-s", help="Job board source name ('all' or comma-separated, e.g. 'himalayas,jobicy')"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Number of days cutoff for recent postings"),
) -> None:
    """Scrape recent jobs from target job boards into PostgreSQL."""
    if days < 1:
        raise typer.BadParameter("--days must be at least 1")

    available = list_connectors()
    if source.lower() == "all":
        sources_to_run = available
    else:
        requested = [s.strip().lower() for s in source.split(",")]
        unknown = sorted(set(requested) - set(available))
        if unknown:
            raise typer.BadParameter(f"unknown source(s): {', '.join(unknown)}. Available: {', '.join(available)}")
        sources_to_run = requested

    if asyncio.run(_run_scrape(sources_to_run, days, include_catalog_status=source.lower() == "all")):
        raise typer.Exit(1)


@app.command()
def stop(
    run_id: UUID | None = typer.Option(None, "--run-id", help="Execution ID; omit to stop the active CLI or web scrape."),
) -> None:
    """Finish the current batch, save collected jobs, then stop the active scrape."""
    async def request() -> None:
        manager = DatabaseSessionManager()
        try:
            stopped_id = await request_scrape_stop(manager, run_id)
            if stopped_id is None:
                console.print("[yellow]No active scrape found.[/yellow]")
                raise typer.Exit(1)
            console.print(f"[yellow]Stop requested for {stopped_id}. Waiting for the current batch to finish.[/yellow]")
        finally:
            await manager.close()
    asyncio.run(request())


@app.command()
def export(
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
    days: int = typer.Option(7, "--days", "-d", help="Only export jobs posted in the last X days"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Export format: jsonl or parquet"),
) -> None:
    """Export scraped jobs to an ML-ready dataset file."""
    if days < 1:
        raise typer.BadParameter("--days must be at least 1")
    if format not in {"jsonl", "parquet"}:
        raise typer.BadParameter("--format must be jsonl or parquet")
    if format == "parquet" and find_spec("pyarrow") is None:
        raise typer.BadParameter("Parquet export requires: uv run --extra export job-scrapper export ...")
    target = output or f"data/jobs_dataset.{format}"

    async def _export() -> None:
        session_manager = DatabaseSessionManager()
        try:
            console.print(f"[cyan]Exporting jobs (posted within last {days} days) to {target}...[/cyan]")
            exporter = export_jobs_to_parquet if format == "parquet" else export_jobs_to_jsonl
            count = await exporter(session_manager, output_path=target, max_days=days)
            console.print(f"[bold green]Successfully exported {count} jobs to {target}[/bold green]")
        finally:
            await session_manager.close()

    asyncio.run(_export())


@app.command()
def status() -> None:
    """Show current database job counts and source breakdowns."""
    async def _status() -> None:
        session_manager = DatabaseSessionManager()
        try:
            async with session_manager.session() as session:
                stmt = select(JobModel.source, func.count(JobModel.id)).group_by(JobModel.source)
                result = await session.execute(stmt)
                rows = result.all()

                table = Table(title="Database Job Breakdown")
                table.add_column("Source", style="cyan")
                table.add_column("Total Postings", justify="right", style="green")

                total = 0
                for src, count in rows:
                    table.add_row(src, str(count))
                    total += count

                console.print(table)
                console.print(f"\n[bold]Total Stored Postings: {total}[/bold]")
        finally:
            await session_manager.close()

    asyncio.run(_status())


@app.command()
def reset() -> None:
    """Delete collected jobs, sightings, and scrape runs from the configured database."""
    async def _reset() -> None:
        session_manager = DatabaseSessionManager()
        try:
            async with scrape_lock(session_manager), session_manager.session() as session:
                await session.execute(text("TRUNCATE TABLE job_sightings, jobs, scrape_runs, scrape_executions"))
                await session.commit()
            console.print("[green]Cleared jobs, sightings, and scrape runs.[/green]")
        except ScrapeBusyError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(1)
        finally:
            await session_manager.close()

    asyncio.run(_reset())


@app.command("api")
@app.command("web")
def serve_api(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host address."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number."),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload on code changes."),
) -> None:
    """Start the FastAPI backend service at http://127.0.0.1:8000."""
    if find_spec("fastapi") is None or find_spec("uvicorn") is None:
        raise typer.BadParameter("API server requires: uv run --extra web job-scrapper api")
    import uvicorn
    if reload:
        uvicorn.run("job_scrapper.web:create_app", factory=True, host=host, port=port, reload=True)
    else:
        from job_scrapper.web import create_app
        uvicorn.run(create_app(), host=host, port=port, workers=1)


if __name__ == "__main__":
    app()
