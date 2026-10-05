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


async def _run_scrape(sources: list[str], days: int) -> None:
    session_manager = DatabaseSessionManager()
    sink = PostgresJobSink(session_manager)

    table = Table(title=f"Scrape Results (Cutoff: Last {days} Days)")
    table.add_column("Source", style="cyan")
    table.add_column("Found", justify="right")
    table.add_column("New Inserted", justify="right", style="green")
    table.add_column("Skipped / Duplicate", justify="right", style="dim")

    for source_name in sources:
        try:
            connector = get_connector(source_name)
            console.print(f"[bold blue]Scraping {source_name}...[/bold blue]")
            stats = await connector.scrape(sink=sink, max_days=days)
            table.add_row(
                source_name,
                str(stats["found"]),
                str(stats["inserted"]),
                str(stats["skipped"]),
            )
        except Exception as e:
            console.print(f"[bold red]Error scraping {source_name}: {e}[/bold red]")

    console.print(table)
    total_jobs = await sink.count()
    console.print(f"\n[bold green]Total jobs stored in database: {total_jobs}[/bold green]")
    await session_manager.close()


@app.command()
def scrape(
    source: str = typer.Option(
        "all", "--source", "-s", help="Job board source name ('all' or comma-separated, e.g. 'himalayas,jobicy')"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Number of days cutoff for recent postings"),
) -> None:
    """Scrape recent jobs from target job boards into PostgreSQL."""
    available = list_connectors()
    if source.lower() == "all":
        sources_to_run = available
    else:
        requested = [s.strip().lower() for s in source.split(",")]
        sources_to_run = [s for s in requested if s in available]
        if not sources_to_run:
            console.print(f"[red]No valid sources provided. Available: {', '.join(available)}[/red]")
            raise typer.Exit(1)

    asyncio.run(_run_scrape(sources_to_run, days))


@app.command()
def export(
    output: str = typer.Option("data/jobs_dataset.jsonl", "--output", "-o", help="Output file path"),
    days: int = typer.Option(7, "--days", "-d", help="Only export jobs posted in the last X days"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Export format (currently 'jsonl')"),
) -> None:
    """Export scraped jobs to an ML-ready dataset file."""
    async def _export() -> None:
        session_manager = DatabaseSessionManager()
        console.print(f"[cyan]Exporting jobs (posted within last {days} days) to {output}...[/cyan]")
        count = await export_jobs_to_jsonl(session_manager, output_path=output, max_days=days)
        console.print(f"[bold green]Successfully exported {count} jobs to {output}[/bold green]")
        await session_manager.close()

    asyncio.run(_export())


@app.command()
def status() -> None:
    """Show current database job counts and source breakdowns."""
    async def _status() -> None:
        session_manager = DatabaseSessionManager()
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
        await session_manager.close()

    asyncio.run(_status())


if __name__ == "__main__":
    app()
