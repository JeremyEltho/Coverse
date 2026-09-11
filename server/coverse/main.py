"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ai.registry import reset_provider
from .api import health, rooms
from .config import get_settings
from .ws import chat, sync
from .ws.rooms import registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    await registry.start_reaper()
    logging.getLogger(__name__).info(
        "Coverse up: provider=%s model=%s",
        settings.ai_provider,
        settings.resolved_model,
    )
    try:
        yield
    finally:
        await registry.close_all()
        await reset_provider()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Coverse", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(rooms.router)
    app.include_router(sync.router)
    app.include_router(chat.router)
    return app


app = create_app()
