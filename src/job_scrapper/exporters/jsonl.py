"""Atomic, streaming JSONL export for ML datasets."""

from contextlib import aclosing
import json
import os
from pathlib import Path
import tempfile

from job_scrapper.exporters._rows import iter_job_batches, record_from_row
from job_scrapper.storage.postgres.session import DatabaseSessionManager


async def export_jobs_to_jsonl(
    session_manager: DatabaseSessionManager,
    output_path: str | Path,
    max_days: int | None = 7,
    limit: int | None = None,
) -> int:
    """Export jobs in 500-row batches, replacing the destination on success."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    count = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            async with aclosing(iter_job_batches(session_manager, max_days, limit)) as batches:
                async for batch in batches:
                    for row in batch:
                        output.write(json.dumps(record_from_row(row), ensure_ascii=False) + "\n")
                        count += 1
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return count
