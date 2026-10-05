"""Atomic, streaming Parquet export with a stable schema."""

from contextlib import aclosing
import json
import os
from pathlib import Path
import tempfile

from job_scrapper.exporters._rows import iter_job_batches, record_from_row
from job_scrapper.storage.postgres.session import DatabaseSessionManager


async def export_jobs_to_parquet(
    session_manager: DatabaseSessionManager,
    output_path: str | Path,
    max_days: int | None = 7,
    limit: int | None = None,
) -> int:
    """Export jobs in 500-row groups; labels are UTF-8 JSON strings."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Parquet export requires the export extra (uv run --extra export)") from exc

    schema = pa.schema([
        ("id", pa.string()),
        ("source", pa.string()),
        ("source_url", pa.string()),
        ("title", pa.string()),
        ("company_name", pa.string()),
        ("description_text", pa.string()),
        ("posted_at", pa.string()),
        ("scraped_at", pa.string()),
        ("labels", pa.string()),
    ])
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    count = 0
    try:
        with pq.ParquetWriter(temp_name, schema=schema) as writer:
            async with aclosing(iter_job_batches(session_manager, max_days, limit)) as batches:
                async for batch in batches:
                    records = [record_from_row(row) for row in batch]
                    columns = {
                        name: [
                            json.dumps(record["labels"], ensure_ascii=False, sort_keys=True)
                            if name == "labels" else record[name]
                            for record in records
                        ]
                        for name in schema.names
                    }
                    writer.write_table(pa.table(columns, schema=schema))
                    count += len(records)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return count
