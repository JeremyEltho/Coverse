"""Maps the AI_PROVIDER env var to a live provider instance."""

from __future__ import annotations

from ..config import Settings, get_settings
from .base import Provider, ProviderError
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenRouterProvider

_instance: Provider | None = None


def build_provider(settings: Settings | None = None) -> Provider:
    settings = settings or get_settings()
    model = settings.resolved_model

    if settings.ai_provider == "mock":
        return MockProvider(delay_ms=settings.mock_delay_ms, model=model)
    if settings.ai_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=model,
            timeout=settings.ai_request_timeout,
        )
    if settings.ai_provider == "openrouter":
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=model,
            base_url=settings.openrouter_base_url,
            timeout=settings.ai_request_timeout,
        )
    raise ProviderError(f"unknown AI_PROVIDER: {settings.ai_provider}")


def get_provider() -> Provider:
    global _instance
    if _instance is None:
        _instance = build_provider()
    return _instance


async def reset_provider() -> None:
    """Drop the cached provider, closing its client. Used by tests and shutdown."""
    global _instance
    if _instance is not None:
        await _instance.aclose()
    _instance = None
