"""Application and worker ports; no transport or database dependencies."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

RunStatus = Literal['queued', 'running', 'stopping', 'stopped', 'completed', 'partial', 'failed', 'interrupted']
ACTIVE_STATUSES = ('queued', 'running', 'stopping')
TERMINAL_STATUSES = ('stopped', 'completed', 'partial', 'failed', 'interrupted')


class RunConflict(Exception):
    """Execution capacity or host ownership conflict."""


class AmbiguousRunSelection(RunConflict):
    """An explicit run ID is needed to select one of several runs."""


class OwnershipLost(Exception):
    """A worker may no longer write progress for its attempt."""


class SourceUnavailable(RuntimeError):
    """A source prerequisite is missing before collection can start."""


class TaskFormatError(Exception):
    """Unsupported or malformed task payload."""


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class StartScrapeCommand(FrozenModel):
    sources: tuple[str, ...] = Field(min_length=1, max_length=100)
    days: int = Field(ge=1, le=365, strict=True)

    @field_validator('sources')
    @classmethod
    def registered_sources(cls, sources: tuple[str, ...]) -> tuple[str, ...]:
        from job_scrapper.connectors.registry import list_connectors
        if set(sources) - set(list_connectors()):
            raise ValueError('Select registered scraper sources.')
        return tuple(dict.fromkeys(sources))


class ScrapeTask(FrozenModel):
    schema_version: Literal[1] = 1
    run_id: UUID
    generation: int = Field(ge=1, strict=True)


class RunSnapshot(FrozenModel):
    id: UUID
    sources: tuple[str, ...]
    days: int
    status: RunStatus
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: int = 0
    results: dict[str, Any]
    error_message: str | None = None
    dispatch_error: str | None = None


class RunClaim(FrozenModel):
    run_id: UUID
    generation: int
    attempt_token: UUID
    command: StartScrapeCommand
    attempt: int


class RunResult(FrozenModel):
    status: Literal['stopped', 'completed', 'partial', 'failed', 'interrupted']
    results: dict[str, Any]
    error_message: str | None = None


class RunCapacity(FrozenModel):
    active: int = Field(ge=1)
    queued: int = Field(ge=1)


class HttpClient(Protocol):
    """Honor execution.cancellation.request_stop_event before sending or retrying.

    Raise RequestStopped for unsent work; allow in-flight requests to finish.
    """

    async def get(self, url: str, **kwargs: Any) -> Any: ...
    async def post(self, url: str, **kwargs: Any) -> Any: ...
    async def close(self) -> None: ...


class RunControl(Protocol):
    capacity: RunCapacity
    def check_health(self) -> None: ...
    async def submit(self, command: StartScrapeCommand) -> RunSnapshot: ...
    async def request_stop(self, run_id: UUID | None = None) -> RunSnapshot | None: ...
    async def get(self, run_id: UUID) -> RunSnapshot | None: ...
    async def list_active(self) -> list[RunSnapshot]: ...
    async def aclose(self) -> None: ...


class TaskDelivery(Protocol):
    task: ScrapeTask
    async def ack(self) -> None: ...
    async def reject(self, *, requeue: bool) -> None: ...


class TaskTransport(Protocol):
    async def publish(self, task: ScrapeTask) -> None: ...
    def deliveries(self) -> AsyncIterator[TaskDelivery]: ...
    async def aclose(self) -> None: ...


class RunStore(Protocol):
    async def create(self, command: StartScrapeCommand) -> RunSnapshot: ...
    async def get(self, run_id: UUID) -> RunSnapshot | None: ...
    async def list_active(self) -> list[RunSnapshot]: ...
    async def request_stop(self, run_id: UUID | None = None) -> RunSnapshot | None: ...
    def claim(self, task: ScrapeTask) -> AbstractAsyncContextManager[RunClaim | None]: ...
    async def stop_requested(self, claim: RunClaim) -> bool: ...
    async def save_progress(self, claim: RunClaim, results: dict[str, Any]) -> None: ...
    async def finish(self, claim: RunClaim, result: RunResult) -> RunSnapshot: ...
    async def schedule_retry(self, claim: RunClaim, error: str, delay_seconds: float) -> None: ...
    async def dispatch_pending(self, publish: Callable[[ScrapeTask], Awaitable[None]], limit: int) -> int: ...
    async def recover_unfinished(self, *, requeue: bool) -> None: ...
