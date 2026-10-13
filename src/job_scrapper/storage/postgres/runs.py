"""PostgreSQL run lifecycle, dispatch intents, and execution ownership."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update

from job_scrapper.execution.contracts import (
    ACTIVE_STATUSES, AmbiguousRunSelection, OwnershipLost, RunCapacity, RunClaim,
    RunConflict, RunResult, RunSnapshot, ScrapeTask, StartScrapeCommand, TERMINAL_STATUSES,
)
from job_scrapper.storage.postgres.models import ScrapeDispatchModel, ScrapeExecutionModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager

RESET_LOCK_KEY = 726384102  # Existing exclusive reset key; attempts hold shared locks.
HOST_LOCK_KEY = 726384103
CONTROL_LOCK_KEY = 726384104


def now() -> datetime:
    return datetime.now(timezone.utc)


def settle_source_results(results: dict[str, Any], status: str) -> dict[str, Any]:
    """Preserve finished sources and counters when an attempt ends externally."""
    source_status = 'pending' if status == 'queued' else 'failed' if status == 'partial' else status
    return {
        source: {**stats, 'status': source_status} if stats.get('status') in ('pending', 'running') else stats
        for source, stats in results.items()
    }


def snapshot(row: ScrapeExecutionModel) -> RunSnapshot:
    return RunSnapshot(
        id=row.id, sources=tuple(row.sources), days=row.days, status=row.status,
        queued_at=row.queued_at, started_at=row.started_at, finished_at=row.finished_at,
        attempts=row.attempts, results={
            source: {**stats, 'status': 'stopped' if row.status == 'queued' else 'stopping'}
            if source in row.stopped_sources and stats.get('status') in ('pending', 'running') else stats
            for source, stats in row.results.items()
        }, error_message=row.error_message,
    )


@asynccontextmanager
async def advisory_guard(manager: DatabaseSessionManager, key: int, *, shared: bool = False,
                         wait: bool = False, wait_timeout: int = 30):
    suffix = '_shared' if shared else ''
    async with manager.engine.connect() as connection:
        try:
            if shared:
                await connection.execute(text('SELECT pg_advisory_lock_shared(:key)'), {'key': key})
                acquired = True
            elif wait:
                await connection.execute(text(f"SET LOCAL lock_timeout = '{wait_timeout}s'"))
                await connection.execute(text('SELECT pg_advisory_lock(:key)'), {'key': key})
                acquired = True
            else:
                acquired = await connection.scalar(
                    text(f'SELECT pg_try_advisory_lock{suffix}(:key)'), {'key': key}
                )
            await connection.commit()
        except BaseException:
            await connection.invalidate()
            raise
        if not acquired:
            raise RunConflict('Another execution host or database reset is already running.')
        try:
            yield connection
        finally:
            try:
                await connection.execute(text(f'SELECT pg_advisory_unlock{suffix}(:key)'), {'key': key})
                await connection.commit()
            except BaseException:
                await connection.invalidate()
                raise


def host_ownership(manager: DatabaseSessionManager):
    return advisory_guard(manager, HOST_LOCK_KEY, wait=True)


def reset_guard(manager: DatabaseSessionManager):
    return advisory_guard(manager, RESET_LOCK_KEY)


class PostgresRunStore:
    def __init__(self, manager: DatabaseSessionManager, capacity: RunCapacity, mode: str = 'memory'):
        self.manager = manager
        self.capacity = capacity
        self.mode = mode
        self.ownership_lost = asyncio.Event()

    async def create(self, command: StartScrapeCommand) -> RunSnapshot:
        async with self.manager.session() as session:
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': CONTROL_LOCK_KEY})
            other_mode = await session.scalar(select(ScrapeExecutionModel.id).where(
                ScrapeExecutionModel.status.in_(ACTIVE_STATUSES), ScrapeExecutionModel.executor_mode != self.mode
            ).limit(1))
            if other_mode is not None:
                raise RunConflict('Finish unfinished runs before changing executor mode.')
            queued = await session.scalar(select(func.count()).select_from(ScrapeExecutionModel).where(
                ScrapeExecutionModel.status.in_(ACTIVE_STATUSES)
            ))
            if queued >= self.capacity.queued:
                raise RunConflict(f'The backlog is full ({self.capacity.queued} unfinished runs). Wait for a run to finish.')
            row = ScrapeExecutionModel(
                id=uuid4(), sources=list(command.sources), days=command.days, status='queued',
                queued_at=now(), executor_mode=self.mode, attempts=0,
                results={source: {'status': 'pending'} for source in command.sources},
            )
            session.add(row)
            await session.flush()
            session.add(ScrapeDispatchModel(run_id=row.id, generation=1, dispatched_generation=0, available_at=now()))
            await session.commit()
            return snapshot(row)

    async def request_source_stop(self, run_id: UUID, source: str) -> RunSnapshot | None:
        async with self.manager.session() as session:
            row = await session.scalar(select(ScrapeExecutionModel).where(
                ScrapeExecutionModel.id == run_id
            ).with_for_update())
            if row is None:
                return None
            if source not in row.sources:
                raise RunConflict('This source is not part of the scrape run.')
            if row.status not in ACTIVE_STATUSES:
                raise RunConflict('This scrape is no longer active. Refresh run history.')
            if source in row.stopped_sources:
                return snapshot(row)
            if row.results.get(source, {}).get('status') not in ('pending', 'running'):
                raise RunConflict('This source has already finished. Refresh run details.')
            # Separate control state from worker-owned progress so saves cannot erase a stop.
            row.stopped_sources = [*row.stopped_sources, source]
            if row.status == 'queued':
                row.results = {**row.results, source: {**row.results[source], 'status': 'stopped'}}
                if set(row.stopped_sources) == set(row.sources):
                    row.status, row.finished_at = 'stopped', now()
            await session.commit()
            return snapshot(row)

    async def get(self, run_id: UUID) -> RunSnapshot | None:
        async with self.manager.session() as session:
            row = await session.get(ScrapeExecutionModel, run_id)
            if row is None:
                return None
            dispatch = await session.get(ScrapeDispatchModel, run_id)
            return snapshot(row).model_copy(update={'dispatch_error': dispatch.error_message if dispatch else None})

    async def list_page(self, *, offset: int, limit: int) -> tuple[int, list[RunSnapshot]]:
        async with self.manager.session() as session:
            total = await session.scalar(select(func.count()).select_from(ScrapeExecutionModel))
            rows = await session.execute(
                select(ScrapeExecutionModel, ScrapeDispatchModel.error_message)
                .outerjoin(ScrapeDispatchModel)
                .order_by(ScrapeExecutionModel.queued_at.desc(), ScrapeExecutionModel.id.desc())
                .offset(offset).limit(limit)
            )
            items = [snapshot(row).model_copy(update={'dispatch_error': error}) for row, error in rows]
            return total or 0, items

    async def list_active(self) -> list[RunSnapshot]:
        async with self.manager.session() as session:
            rows = await session.execute(select(ScrapeExecutionModel, ScrapeDispatchModel.error_message).outerjoin(ScrapeDispatchModel).where(
                ScrapeExecutionModel.status.in_(ACTIVE_STATUSES)
            ).order_by(ScrapeExecutionModel.queued_at, ScrapeExecutionModel.id))
            return [snapshot(row).model_copy(update={'dispatch_error': error}) for row, error in rows]

    async def request_stop(self, run_id: UUID | None = None) -> RunSnapshot | None:
        async with self.manager.session() as session:
            # Admission and ID-less stop use the same lock: selection is atomic.
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': CONTROL_LOCK_KEY})
            statement = select(ScrapeExecutionModel).where(ScrapeExecutionModel.status.in_(ACTIVE_STATUSES))
            if run_id is not None:
                statement = statement.where(ScrapeExecutionModel.id == run_id)
            rows = list(await session.scalars(statement.order_by(ScrapeExecutionModel.id).with_for_update()))
            if len(rows) > 1:
                raise AmbiguousRunSelection('Several runs are active. Supply --run-id to stop one.')
            if not rows:
                return None
            row = rows[0]
            if row.status == 'queued':
                row.status, row.finished_at = 'stopped', now()
                row.results = settle_source_results(row.results, row.status)
            else:
                row.status = 'stopping'
            await session.commit()
            return snapshot(row)

    @asynccontextmanager
    async def claim(self, task: ScrapeTask) -> AsyncIterator[RunClaim | None]:
        if self.ownership_lost.is_set():
            raise OwnershipLost('Worker ownership was lost.')
        async with advisory_guard(self.manager, RESET_LOCK_KEY, shared=True) as connection:
            async with self.manager.session() as session:
                row = await session.scalar(select(ScrapeExecutionModel).where(
                    ScrapeExecutionModel.id == task.run_id
                ).with_for_update())
                dispatch = await session.get(ScrapeDispatchModel, task.run_id)
                claim = None
                if row and dispatch and row.status == 'queued' and row.executor_mode == self.mode and dispatch.generation == task.generation:
                    if dispatch.available_at <= now():
                        row.status, row.started_at = 'running', now()
                        row.attempts += 1
                        row.attempt_token = uuid4()
                        row.error_message = None
                        row.results = {source: {'status': 'stopped' if source in row.stopped_sources else 'pending'}
                                       for source in row.sources}
                        claim = RunClaim(run_id=row.id, generation=task.generation, attempt_token=row.attempt_token,
                                         command=StartScrapeCommand(sources=tuple(row.sources), days=row.days), attempt=row.attempts)
                await session.commit()

            async def watch_guard():
                while True:
                    await asyncio.sleep(1)
                    try:
                        if connection.invalidated:
                            raise OwnershipLost('Execution guard was lost.')
                        await connection.execute(text('SELECT 1'))
                        await connection.commit()
                    except Exception:
                        self.ownership_lost.set()
                        return

            watcher = asyncio.create_task(watch_guard()) if claim else None
            try:
                yield claim
            finally:
                if watcher:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)

    def _owned(self, claim: RunClaim):
        return (ScrapeExecutionModel.id == claim.run_id,
                ScrapeExecutionModel.attempt_token == claim.attempt_token,
                ScrapeExecutionModel.status.in_(('running', 'stopping')))

    async def stop_requests(self, claim: RunClaim) -> tuple[bool, set[str]]:
        if self.ownership_lost.is_set():
            raise OwnershipLost('Worker ownership was lost.')
        async with self.manager.session() as session:
            row = (await session.execute(select(ScrapeExecutionModel.status, ScrapeExecutionModel.stopped_sources)
                                         .where(*self._owned(claim)))).one_or_none()
        if row is None:
            raise OwnershipLost('Execution attempt is no longer owned.')
        return row.status == 'stopping', set(row.stopped_sources)

    async def save_progress(self, claim: RunClaim, results: dict[str, Any]) -> None:
        if self.ownership_lost.is_set():
            raise OwnershipLost('Worker ownership was lost.')
        async with self.manager.session() as session:
            result = await session.execute(update(ScrapeExecutionModel).where(*self._owned(claim)).values(results=results))
            if result.rowcount != 1:
                raise OwnershipLost('Execution attempt is no longer owned.')
            await session.commit()

    async def finish(self, claim: RunClaim, result: RunResult) -> RunSnapshot:
        async with self.manager.session() as session:
            row = await session.scalar(select(ScrapeExecutionModel).where(*self._owned(claim)).with_for_update())
            if row is None or self.ownership_lost.is_set():
                raise OwnershipLost('Execution attempt is no longer owned.')
            row.status = 'stopped' if row.status == 'stopping' else result.status
            row.results = settle_source_results(result.results, row.status)
            row.error_message = result.error_message
            row.finished_at, row.attempt_token = now(), None
            await session.commit()
            return snapshot(row)

    async def schedule_retry(self, claim: RunClaim, error: str, delay_seconds: float) -> None:
        async with self.manager.session() as session:
            row = await session.scalar(select(ScrapeExecutionModel).where(*self._owned(claim)).with_for_update())
            if row is None or self.ownership_lost.is_set():
                raise OwnershipLost('Execution attempt is no longer owned.')
            row.error_message, row.attempt_token = error, None
            if row.status == 'stopping' or row.attempts >= 3:
                row.status = 'stopped' if row.status == 'stopping' else 'failed'
                row.finished_at = now()
            else:
                row.status, row.started_at = 'queued', None
                dispatch = await session.get(ScrapeDispatchModel, row.id)
                dispatch.generation += 1
                dispatch.available_at = now() + timedelta(seconds=delay_seconds)
            row.results = settle_source_results(row.results, row.status)
            await session.commit()

    async def dispatch_pending(self, publish: Callable[[ScrapeTask], Awaitable[None]], limit: int) -> int:
        count = 0
        # One transaction per publish avoids holding an entire batch of row locks.
        for _ in range(limit):
            async with self.manager.session() as session:
                dispatch = await session.scalar(select(ScrapeDispatchModel).join(ScrapeExecutionModel).where(
                    ScrapeExecutionModel.status == 'queued', ScrapeExecutionModel.executor_mode == self.mode,
                    ScrapeDispatchModel.generation > ScrapeDispatchModel.dispatched_generation,
                    ScrapeDispatchModel.available_at <= now(),
                ).order_by(ScrapeDispatchModel.available_at, ScrapeDispatchModel.run_id)
                  .with_for_update(of=ScrapeDispatchModel, skip_locked=True).limit(1))
                if dispatch is None:
                    break
                try:
                    await asyncio.wait_for(publish(ScrapeTask(run_id=dispatch.run_id, generation=dispatch.generation)), timeout=2)
                except asyncio.QueueFull:
                    break
                except Exception as error:
                    dispatch.error_message = f'Dispatch deferred: {type(error).__name__}'
                    await session.commit()
                    break
                dispatch.dispatched_generation = dispatch.generation
                dispatch.error_message = None
                await session.commit()
                count += 1
        return count

    async def recover_unfinished(self, *, requeue: bool) -> None:
        async with self.manager.session() as session:
            rows = list(await session.scalars(select(ScrapeExecutionModel).where(
                ScrapeExecutionModel.status.in_(ACTIVE_STATUSES)
            ).with_for_update()))
            if any(row.executor_mode != self.mode for row in rows):
                raise RunConflict('Finish unfinished runs before changing executor mode.')
            for row in rows:
                if row.status == 'stopping':
                    row.status, row.finished_at = 'stopped', now()
                elif not requeue:
                    row.status, row.finished_at = 'interrupted', now()
                    row.error_message = 'Memory execution host stopped before completion.'
                elif row.status == 'running':
                    row.error_message = 'Worker stopped before completion; retrying infrastructure interruption.'
                    if row.attempts >= 3:
                        row.status, row.finished_at = 'failed', now()
                    else:
                        row.status, row.started_at = 'queued', None
                        dispatch = await session.get(ScrapeDispatchModel, row.id)
                        dispatch.generation += 1
                        dispatch.available_at = now() + timedelta(seconds=5 if row.attempts == 1 else 30)
                row.attempt_token = None
                if row.status in TERMINAL_STATUSES or row.status == 'queued':
                    row.results = settle_source_results(row.results, row.status)
            await session.commit()
