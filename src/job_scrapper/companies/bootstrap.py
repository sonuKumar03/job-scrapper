"""Database initialization wiring shared by setup, API, CLI and workers."""

import asyncio
import logging

from job_scrapper.companies.contracts import SeedReport
from job_scrapper.companies.seed import load_seed
from job_scrapper.storage.postgres.companies import PostgresCompanyTargetRepository
from job_scrapper.storage.postgres.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


async def initialize_company_catalog(manager: DatabaseSessionManager) -> SeedReport:
    companies, targets = load_seed()
    report = await PostgresCompanyTargetRepository(manager).ensure_seed(companies, targets)
    for conflict in report.conflicts:
        logger.warning('Company seed conflict: %s', conflict)
    return report


async def main() -> None:
    manager = DatabaseSessionManager()
    try:
        report = await initialize_company_catalog(manager)
        print(f'Company seed: {report.inserted_companies} companies and {report.inserted_targets} boards inserted; {len(report.conflicts)} conflicts preserved.')
    finally:
        await manager.close()


if __name__ == '__main__':
    asyncio.run(main())
