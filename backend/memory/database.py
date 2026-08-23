"""Database engine/session management (SQLAlchemy 2.x async + aiosqlite)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.logging import get_logger
from backend.memory.models import Base

logger = get_logger("griffin.db")


class Database:
    """Owns the async engine and session factory for one application instance."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = create_async_engine(url, future=True)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Idempotent migration: existing dev databases predate the run_id
            # column on the events table. create_all won't add it, so add it
            # here when missing (SQLite-only — fine for this app).
            cols = (await conn.execute(text("PRAGMA table_info(events)"))).all()
            names = {row[1] for row in cols}
            if names and "run_id" not in names:
                await conn.execute(text("ALTER TABLE events ADD COLUMN run_id VARCHAR"))
                logger.info("db.migrated", extra={"table": "events", "column": "run_id"})
        logger.info("db.tables_ready")

    async def dispose(self) -> None:
        await self.engine.dispose()

    def session(self) -> AsyncSession:
        return self.session_factory()
