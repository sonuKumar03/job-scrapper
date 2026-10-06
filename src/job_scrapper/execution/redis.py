"""Redis Streams task transport; broker objects never cross this boundary."""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator
from uuid import uuid4

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from job_scrapper.execution.contracts import ScrapeTask

logger = logging.getLogger(__name__)
GROUP = 'scrape-workers-v1'


class RedisDelivery:
    def __init__(self, transport: 'RedisTaskTransport', entry_id: str, task: ScrapeTask):
        self.task, self._transport, self._id, self._settled = task, transport, entry_id, False

    async def ack(self) -> None:
        if not self._settled:
            async with self._transport._client.pipeline(transaction=True) as pipe:
                pipe.xack(self._transport.stream, GROUP, self._id)
                pipe.xdel(self._transport.stream, self._id)
                await pipe.execute()
            self._settled = True

    async def reject(self, *, requeue: bool) -> None:
        if not requeue:
            await self._transport.dead_letter(self._id, self.task.model_dump_json())
            self._settled = True
        # Requeue retains the pending entry; the next sole host reclaims it.


class RedisTaskTransport:
    def __init__(self, url: str, stream: str):
        self.stream = stream
        self._client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2,
                                      socket_timeout=3, health_check_interval=15)
        self._closed = False
        self._recovered: deque = deque()

    async def publish(self, task: ScrapeTask) -> None:
        if self._closed:
            raise RuntimeError('Task transport is closed.')
        await self._client.xadd(self.stream, {'task': task.model_dump_json()})

    async def prepare_consumer(self) -> None:
        try:
            await self._client.xgroup_create(self.stream, GROUP, id='0-0', mkstream=True)
        except ResponseError as error:
            if not str(error).startswith('BUSYGROUP'):
                raise
        # Only invoked after database host ownership has been acquired. No live
        # sibling host exists, so pending entries can be reclaimed without an
        # idle timeout that would mistake long scrapes for crashed workers.
        consumer = f'recovery-{uuid4()}'
        cursor = '0-0'
        while True:
            cursor, entries, *_ = await self._client.xautoclaim(self.stream, GROUP, consumer, 0, cursor, count=100)
            self._recovered.extend(entries)
            if cursor == '0-0':
                break

    async def dead_letter(self, entry_id: str, payload: str) -> None:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.xadd(f'{self.stream}.dead', {'entry_id': entry_id, 'task': payload[:4096]}, maxlen=1000)
            pipe.xack(self.stream, GROUP, entry_id)
            pipe.xdel(self.stream, entry_id)
            await pipe.execute()

    async def deliveries(self) -> AsyncIterator[RedisDelivery]:
        consumer = f'worker-{uuid4()}'
        while not self._closed:
            if self._recovered:
                entries = [self._recovered.popleft()]
            else:
                response = await self._client.xreadgroup(GROUP, consumer, {self.stream: '>'}, count=1, block=500)
                entries = response[0][1] if response else []
            for entry_id, fields in entries:
                try:
                    task = ScrapeTask.model_validate_json(fields.get('task', ''))
                except ValidationError:
                    await self.dead_letter(entry_id, fields.get('task', ''))
                    logger.warning('Rejected malformed scrape task: %s', entry_id)
                    continue
                yield RedisDelivery(self, entry_id, task)
            if not entries:
                await asyncio.sleep(0)

    async def aclose(self) -> None:
        self._closed = True
        await self._client.aclose()
