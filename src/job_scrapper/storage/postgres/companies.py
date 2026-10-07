"""PostgreSQL company catalog adapter; runtime reads never load packaged seed."""

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from job_scrapper.companies.contracts import Company, CompanyCatalogUnavailable, CompanyTarget, SeedReport
from job_scrapper.storage.postgres.models import CompanyModel, CompanyTargetModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager

SEED_LOCK_KEY = 731862041


class PostgresCompanyTargetRepository:
    def __init__(self, manager: DatabaseSessionManager) -> None:
        self.manager = manager

    async def ensure_seed(self, companies: tuple[Company, ...], targets: tuple[CompanyTarget, ...]) -> SeedReport:
        try:
            async with self.manager.session() as session, session.begin():
                await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': SEED_LOCK_KEY})
                inserted_companies = []
                if companies:
                    inserted_companies = (await session.scalars(
                        insert(CompanyModel).values([c.model_dump() for c in companies])
                        .on_conflict_do_nothing().returning(CompanyModel.company_key)
                    )).all()
                inserted_targets = []
                if targets:
                    inserted_targets = (await session.scalars(
                        insert(CompanyTargetModel).values([t.model_dump(exclude={'company_name'}) for t in targets])
                        .on_conflict_do_nothing().returning(CompanyTargetModel.id)
                    )).all()
                existing_companies = {c.company_key: c for c in (await session.scalars(select(CompanyModel))).all()}
                existing_targets = {(t.provider, t.account_key): t for t in (await session.scalars(select(CompanyTargetModel))).all()}
                conflicts = []
                for c in companies:
                    current = existing_companies[c.company_key]
                    if (current.company_name, current.source_url) != (c.company_name, c.source_url):
                        conflicts.append(f'company {c.company_key}: existing identity preserved')
                for t in targets:
                    current = existing_targets[t.provider, t.account_key]
                    if (current.company_key, current.board_url) != (t.company_key, t.board_url):
                        conflicts.append(f'board {t.provider}/{t.account_key}: existing ownership/URL preserved')
                return SeedReport(inserted_companies=len(inserted_companies), inserted_targets=len(inserted_targets), conflicts=tuple(conflicts))
        except SQLAlchemyError as error:
            raise CompanyCatalogUnavailable('Company catalog initialization failed. Run make migrate and check PostgreSQL.') from error

    async def list_enabled(self, provider: str) -> tuple[CompanyTarget, ...]:
        try:
            async with self.manager.session() as session:
                rows = (await session.execute(
                    select(CompanyTargetModel, CompanyModel.company_name)
                    .join(CompanyModel, CompanyModel.company_key == CompanyTargetModel.company_key)
                    .where(CompanyTargetModel.provider == provider, CompanyTargetModel.enabled.is_(True))
                    .order_by(CompanyTargetModel.account_key)
                )).all()
                return tuple(CompanyTarget(
                    company_key=t.company_key, company_name=name, provider=t.provider,
                    account_key=t.account_key, board_url=t.board_url, verification_status=t.verification_status,
                    enabled=t.enabled, provenance=t.provenance,
                ) for t, name in rows)
        except SQLAlchemyError as error:
            raise CompanyCatalogUnavailable('Company targets unavailable. Check PostgreSQL.') from error

    async def status_counts(self) -> dict[str, int]:
        try:
            async with self.manager.session() as session:
                counts = {'companies': await session.scalar(select(func.count()).select_from(CompanyModel)) or 0,
                          'boards': await session.scalar(select(func.count()).select_from(CompanyTargetModel)) or 0,
                          'enabled_boards': await session.scalar(select(func.count()).select_from(CompanyTargetModel).where(CompanyTargetModel.enabled.is_(True))) or 0}
                rows = (await session.execute(select(CompanyTargetModel.verification_status, func.count())
                                               .group_by(CompanyTargetModel.verification_status))).all()
                counts.update({f'boards_{status}': count for status, count in rows})
                return counts
        except SQLAlchemyError as error:
            raise CompanyCatalogUnavailable('Company catalog counts unavailable.') from error
