"""Health and diagnostics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..ai.registry import get_provider
from ..config import get_settings
from ..ws.rooms import registry

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    provider = get_provider()
    ok, detail = await provider.health()
    return {
        "status": "ok" if ok else "degraded",
        "provider": {
            "name": settings.ai_provider,
            "model": settings.resolved_model,
            "ok": ok,
            "detail": detail,
        },
        "rooms": registry.active,
    }
