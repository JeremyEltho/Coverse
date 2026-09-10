"""Ollama, for running a real model locally with no API key.

Ollama exposes an OpenAI-compatible endpoint at /v1, which is what we use, but it
gets its own class so health checks can hit the native /api/tags endpoint and give
a genuinely useful error when the daemon is down or the model was never pulled.
"""

from __future__ import annotations

import httpx

from .base import ProviderError
from .openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"

    def __init__(self, *, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.native_base_url = base_url.rstrip("/")
        super().__init__(
            base_url=f"{self.native_base_url}/v1",
            model=model,
            api_key="ollama",  # required by the endpoint, value ignored
            timeout=timeout,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            response = await self._get_client().get(f"{self.native_base_url}/api/tags")
        except httpx.HTTPError as exc:
            return False, (
                f"ollama unreachable at {self.native_base_url} ({exc}). Is `ollama serve` running?"
            )

        if response.status_code >= 400:
            return False, f"ollama returned {response.status_code}"

        installed = [m.get("name", "") for m in response.json().get("models", [])]
        # Tags carry a `:latest` suffix that users rarely type.
        if not any(name.split(":")[0] == self.model.split(":")[0] for name in installed):
            return False, (
                f"model '{self.model}' is not installed. Run: ollama pull {self.model}. "
                f"Installed: {', '.join(installed) or 'none'}"
            )
        return True, f"ollama ready with {self.model}"

    async def ensure_model(self) -> None:
        ok, detail = await self.health()
        if not ok:
            raise ProviderError(detail, provider=self.name)
