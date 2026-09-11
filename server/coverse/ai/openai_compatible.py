"""Shared client for the OpenAI-compatible chat completions API.

OpenRouter, LM Studio, llama.cpp's server and vLLM all speak this, so they differ
only in base URL, auth header and default model.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import Delta, Message, ModelInfo, Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def stream(self, messages: list[Message], **opts: Any) -> AsyncIterator[Delta]:
        payload = {
            "model": opts.get("model") or self.model,
            "messages": [m.to_openai() for m in messages],
            "stream": True,
            "temperature": opts.get("temperature", 0.7),
            "max_tokens": opts.get("max_tokens", 1024),
        }

        client = self._get_client()
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")[:500]
                    raise ProviderError(
                        f"{self.name} returned {response.status_code}: {body}",
                        provider=self.name,
                        retryable=response.status_code in (429, 500, 502, 503, 504),
                    )

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    text = (choices[0].get("delta") or {}).get("content") or ""
                    if text:
                        yield Delta(text=text)

            yield Delta(done=True, meta={"model": payload["model"], "provider": self.name})
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self.name} request failed: {exc}", provider=self.name, retryable=True
            ) from exc

    async def list_models(self) -> list[ModelInfo]:
        """The provider's catalogue, newest-looking first.

        Pricing comes back as a per-token string, which is unreadable at
        catalogue scale, so it is converted to price per million tokens here
        rather than in the UI.
        """
        try:
            response = await self._get_client().get(
                f"{self.base_url}/models", headers=self._headers()
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(
                f"could not load the model list: {exc}", provider=self.name, retryable=True
            ) from exc

        models: list[ModelInfo] = []
        for entry in payload.get("data", []):
            model_id = entry.get("id")
            if not model_id:
                continue
            pricing = entry.get("pricing") or {}
            models.append(
                ModelInfo(
                    id=str(model_id),
                    name=str(entry.get("name") or model_id),
                    context_length=entry.get("context_length"),
                    prompt_price=_per_million(pricing.get("prompt")),
                    completion_price=_per_million(pricing.get("completion")),
                )
            )
        models.sort(key=lambda m: m.name.lower())
        return models

    async def health(self) -> tuple[bool, str]:
        try:
            response = await self._get_client().get(
                f"{self.base_url}/models", headers=self._headers()
            )
            if response.status_code < 400:
                return True, f"{self.name} reachable"
            return False, f"{self.name} returned {response.status_code}"
        except httpx.HTTPError as exc:
            return False, f"{self.name} unreachable: {exc}"

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def _per_million(value: object) -> float | None:
    """Convert a per-token price to price per million tokens.

    Providers report this as a string of a very small number, which is
    unreadable at catalogue scale. Anything unparseable becomes None rather
    than a guess, so the UI can say nothing instead of something wrong.
    """
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float = 120.0) -> None:
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set", provider=self.name)
        super().__init__(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
            # OpenRouter uses these for attribution on their dashboard.
            extra_headers={
                "HTTP-Referer": "https://github.com/JeremyEltho/Coverse",
                "X-Title": "Coverse",
            },
        )
