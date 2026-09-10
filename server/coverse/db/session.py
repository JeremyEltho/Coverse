"""Async engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..config import get_settings
from .models import Base

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


def _engine_config(url: str) -> tuple[str, dict[str, Any]]:
    """Adapt the URL and engine options to the target database.

    Supabase's pooled endpoint (port 6543) is pgbouncer in transaction mode: one
    server connection is handed to whichever client needs it next. Prepared
    statements belong to a session, so asyncpg's habit of preparing everything
    collides there -- the symptom is an intermittent DuplicatePreparedStatement
    error under concurrency rather than a clean failure at startup, which makes
    it worth disabling up front rather than debugging later.

    Both caches have to go: asyncpg's own (`statement_cache_size`, a connect
    argument) and SQLAlchemy's dialect-level one (`prepared_statement_cache_size`,
    read from the URL query string). NullPool then keeps SQLAlchemy from holding
    a second pool of connections on top of the one pgbouncer is already managing.
    """
    kwargs: dict[str, Any] = {"pool_pre_ping": True}

    if _is_postgres(url) and "asyncpg" in url:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query.setdefault("prepared_statement_cache_size", "0")
        url = urlunsplit(parts._replace(query=urlencode(query)))
        kwargs["connect_args"] = {"statement_cache_size": 0}
        kwargs["poolclass"] = NullPool

    return url, kwargs


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url, kwargs = _engine_config(settings.database_url)
        _engine = create_async_engine(url, future=True, **kwargs)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables if they are missing.

    Only for the SQLite default, so `uvicorn coverse.main:app` works with no
    setup at all. Postgres deployments get their schema from
    `supabase/migrations/`, which also carries the row level security policies,
    triggers and `auth.users` foreign keys that the SQLAlchemy models do not
    describe -- running create_all against those would be, at best, a no-op
    issuing DDL on every boot.
    """
    settings = get_settings()
    if _is_postgres(settings.database_url):
        return

    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
