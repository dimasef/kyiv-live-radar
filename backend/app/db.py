from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # A dead idle connection must never reach a request. Both settings matter
    # only on prod Postgres (SQLite's pool holds no network sockets), but they
    # are harmless there — see settings.db_pool_recycle_seconds for the why.
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle_seconds,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a request-scoped async DB session."""
    async with SessionLocal() as session:
        yield session
