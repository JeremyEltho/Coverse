"""The catalogue of models the current provider can be switched to."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..ai.base import ProviderError
from ..ai.registry import get_provider
from ..config import get_settings

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models() -> dict[str, Any]:
    """Available models, plus whichever one is configured as the default.

    A provider that cannot reach its catalogue is not an error worth failing the
    page over: the room still works on the configured model, so the failure is
    reported alongside an empty list and the UI simply does not offer a picker.
    """
    settings = get_settings()
    provider = get_provider()

    try:
        models = [m.to_json() for m in await provider.list_models()]
        error = None
    except ProviderError as exc:
        models, error = [], str(exc)

    return {
        "provider": settings.ai_provider,
        "default": settings.resolved_model,
        "models": models,
        "error": error,
    }
