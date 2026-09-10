from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("MOCK_DELAY_MS", "0")


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch):
    """Give every test its own SQLite file and a fresh settings cache."""
    from coverse import config
    from coverse.db import session as db_session

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp}/test.db")
        config.get_settings.cache_clear()
        db_session._engine = None
        db_session._sessionmaker = None
        yield
        config.get_settings.cache_clear()
        db_session._engine = None
        db_session._sessionmaker = None
