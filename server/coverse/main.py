"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ai.registry import reset_provider
from .api import documents, health
from .config import get_settings
from .db.session import dispose_db, init_db
from .ws import chat, sync
from .ws.rooms import room_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    await init_db()
    logging.getLogger(__name__).info(
        "Coverse up: provider=%s model=%s auth=%s",
        settings.ai_provider,
        settings.resolved_model,
        "dev" if settings.is_dev_auth else "supabase",
    )
    try:
        yield
    finally:
        # Flush every room's buffered updates before the process exits.
        await room_manager.close_all()
        await reset_provider()
        await dispose_db()


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
    app.include_router(documents.router)
    app.include_router(sync.router)
    app.include_router(chat.router)
    return app


app = create_app()
