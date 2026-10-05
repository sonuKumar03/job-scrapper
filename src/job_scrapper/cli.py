"""Typer CLI interface for Job Scrapper."""

import asyncio
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select
import typer
from job_scrapper.connectors.registry import get_connector, list_connectors
from job_scrapper.exporters.jsonl import export_jobs_to_jsonl
from job_scrapper.storage.postgres.models import JobModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.sink import PostgresJobSink

app = typer.Typer(help="High-volume job scraper and ML dataset generator.")
console = Console()


async def _run_scrape(sources: list[str], days: int) -> bool:
    session_manager = DatabaseSessionManager()
    sink = PostgresJobSink(session_manager)

    table = Table(title=f"Scrape Results (Cutoff: Last {days} Days)")
    table.add_column("Source", style="cyan")
    table.add_column("Found", justify="right")
    table.add_column("New Inserted", justify="right", style="green")
    table.add_column("Skipped / Duplicate", justify="right", style="dim")
    table.add_column("Errors", style="red")
    table.add_column("Truncated", style="yellow")
    failed = False
    try:
        for source_name in sources:
            connector = None
            try:
                connector = get_connector(source_name)
                console.print(f"[bold blue]Scraping {source_name}...[/bold blue]")
                stats = await connector.scrape(sink=sink, max_days=days)
                table.add_row(
                    source_name,
                    str(stats["found"]),
                    str(stats["inserted"]),
                    str(stats["skipped"]),
                    "; ".join(stats["errors"]),
                    "yes" if stats["truncated"] else "no",
                )
                failed |= bool(stats["errors"] or stats["truncated"])
            except Exception as e:
                failed = True
                console.print(f"[bold red]Error scraping {source_name}: {type(e).__name__}[/bold red]")
            finally:
                if connector is not None:
                    await connector.close()

        console.print(table)
        total_jobs = await sink.count()
        console.print(f"\n[bold green]Total jobs stored in database: {total_jobs}[/bold green]")
    finally:
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

    if asyncio.run(_run_scrape(sources_to_run, days)):
        raise typer.Exit(1)


@app.command()
def export(
    output: str = typer.Option("data/jobs_dataset.jsonl", "--output", "-o", help="Output file path"),
    days: int = typer.Option(7, "--days", "-d", help="Only export jobs posted in the last X days"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Export format (currently 'jsonl')"),
) -> None:
    """Export scraped jobs to an ML-ready dataset file."""
    if days < 1:
        raise typer.BadParameter("--days must be at least 1")

    async def _export() -> None:
        session_manager = DatabaseSessionManager()
        try:
            console.print(f"[cyan]Exporting jobs (posted within last {days} days) to {output}...[/cyan]")
            count = await export_jobs_to_jsonl(session_manager, output_path=output, max_days=days)
            console.print(f"[bold green]Successfully exported {count} jobs to {output}[/bold green]")
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


if __name__ == "__main__":
    app()
