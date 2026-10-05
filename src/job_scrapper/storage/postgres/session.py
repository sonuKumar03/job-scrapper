"""Database session and connection management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseSessionManager:
    """Manages async PostgreSQL connection engine and sessions."""

    def __init__(self, database_url: str | None = None) -> None:
        raw_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgrespassword@localhost:5432/job_scrapper",
        )
        # Ensure async driver if url starts with postgresql://
        if raw_url.startswith("postgresql://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)

        self.engine: AsyncEngine = create_async_engine(
            raw_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        await self.engine.dispose()
