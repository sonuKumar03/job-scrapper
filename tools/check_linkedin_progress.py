import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from job_scrapper.connectors.linkedin import LinkedInConnector
from job_scrapper.execution.cancellation import RequestStopped
from job_scrapper.storage.memory import InMemoryJobSink


class Client:
    def __init__(self, stop, hold_from=100004):
        self.stop = stop
        self.hold_from = hold_from
        self.hold = asyncio.Event()

    async def get(self, url):
        if '/jobs/search/' in url:
            return SimpleNamespace(text=''.join(
                f'<a href="https://in.linkedin.com/jobs/view/engineer-{i}">Job</a>'
                for i in range(100000, 100011)
            ))
        source_id = int(url.rsplit('-', 1)[1])
        if source_id >= self.hold_from:
            await self.hold.wait()
            if self.stop.is_set():
                raise RequestStopped()
        item = {'@type': 'JobPosting', 'datePosted': datetime.now(timezone.utc).isoformat(),
                'title': 'Engineer', 'hiringOrganization': {'name': 'Example'},
                'description': 'Build reliable software systems.'}
        return SimpleNamespace(text=f'<script type="application/ld+json">{json.dumps(item)}</script>')


async def main():
    stop = asyncio.Event()
    client = Client(stop)
    connector = LinkedInConnector(client)
    connector.SEARCH_QUERIES = ('engineer',)
    connector.MAX_PAGES = 1
    connector.stop_event = stop
    snapshots = []
    async def progress(stats):
        snapshots.append((stats['found'], stats['inserted'], stats['skipped']))
    connector.on_progress = progress
    task = asyncio.create_task(connector.scrape(InMemoryJobSink(), 1))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if snapshots:
            break
    assert snapshots and snapshots[0] == (11, 0, 0), snapshots
    assert not task.done(), 'First-page progress should precede detail completion'
    stop.set()
    client.hold.set()
    result = await task
    assert result['found'] == 11 and result['inserted'] == 4, result
    assert result['skipped'] == 0, result
    assert result['detail_attempted'] == 4, result
    stop = asyncio.Event()
    client = Client(stop, hold_from=100010)
    connector = LinkedInConnector(client)
    connector.SEARCH_QUERIES = ('engineer',)
    connector.MAX_PAGES = 1
    connector.stop_event = stop
    snapshots = []
    connector.on_progress = lambda stats: record(stats, snapshots)
    task = asyncio.create_task(connector.scrape(InMemoryJobSink(), 1))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if any(inserted == 10 for _, inserted, _ in snapshots):
            break
    assert (11, 10, 0) in snapshots and not task.done(), snapshots
    stop.set()
    client.hold.set()
    result = await task
    assert result['inserted'] == 10 and result['skipped'] == 0
    assert result['detail_attempted'] == 10, result
    print('LinkedIn progress and stop counters passed')


async def record(stats, snapshots):
    snapshots.append((stats['found'], stats['inserted'], stats['skipped']))


asyncio.run(main())
