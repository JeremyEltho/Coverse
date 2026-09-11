from __future__ import annotations

import os

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("MOCK_DELAY_MS", "0")


@pytest.fixture(autouse=True)
def _fresh_settings():
    from coverse import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
