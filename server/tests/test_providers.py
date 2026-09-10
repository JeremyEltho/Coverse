"""The OpenAI-compatible streaming client, exercised against a stub server.

Ollama, OpenRouter, LM Studio and llama.cpp all speak this protocol, so these
tests cover the code path that every real model backend actually uses.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from uvicorn import Config, Server

from coverse.ai.base import Message, ProviderError
from coverse.ai.ollama import OllamaProvider
from coverse.ai.openai_compatible import OpenAICompatibleProvider


def build_stub(chunks: list[str], *, status: int = 200, installed: str = "llama3.2") -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completions(request: Request):  # noqa: ANN202
        await request.json()
        if status >= 400:
            return JSONResponse({"error": "boom"}, status_code=status)

        async def stream() -> AsyncIterator[bytes]:
            for chunk in chunks:
                payload = {"choices": [{"delta": {"content": chunk}}]}
                yield f"data: {json.dumps(payload)}\n\n".encode()
                await asyncio.sleep(0)
            # A keepalive and a malformed line: both must be ignored, not crash.
            yield b": keepalive\n\n"
            yield b"data: {not json}\n\n"
            yield b"data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/tags")
    async def tags():  # noqa: ANN202
        return {"models": [{"name": f"{installed}:latest"}]}

    return app


class RunningServer:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __aenter__(self) -> str:
        config = Config(self.app, host="127.0.0.1", port=0, log_level="error")
        self.server = Server(config)
        self.task = asyncio.create_task(self.server.serve())
        # uvicorn exposes a `started` flag rather than an awaitable, so polling
        # is the only way to wait for the port to be bound.
        while not self.server.started:  # noqa: ASYNC110
            await asyncio.sleep(0.02)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def __aexit__(self, *_: object) -> None:
        self.server.should_exit = True
        await self.task


async def test_streaming_deltas_are_parsed_in_order():
    async with RunningServer(build_stub(["Hello", ", ", "world", "."])) as base:
        provider = OpenAICompatibleProvider(base_url=f"{base}/v1", model="m", api_key="k")
        try:
            deltas = [d async for d in provider.stream([Message("user", "hi")])]
        finally:
            await provider.aclose()

    text = "".join(d.text for d in deltas)
    assert text == "Hello, world."
    assert deltas[-1].done is True


async def test_an_http_error_becomes_a_provider_error():
    async with RunningServer(build_stub([], status=500)) as base:
        provider = OpenAICompatibleProvider(base_url=f"{base}/v1", model="m", api_key="k")
        try:
            with pytest.raises(ProviderError) as caught:
                await provider.complete([Message("user", "hi")])
        finally:
            await provider.aclose()

    assert caught.value.retryable is True  # 500 is worth retrying


async def test_a_stream_can_be_cancelled_mid_flight():
    """Cancellation must not leave the HTTP client dangling."""
    async with RunningServer(build_stub(["a"] * 200)) as base:
        provider = OpenAICompatibleProvider(base_url=f"{base}/v1", model="m", api_key="k")

        async def consume() -> None:
            async for _ in provider.stream([Message("user", "hi")]):
                await asyncio.sleep(0.01)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await provider.aclose()


async def test_ollama_health_reports_a_missing_model_usefully():
    async with RunningServer(build_stub([], installed="mistral")) as base:
        provider = OllamaProvider(base_url=base, model="llama3.2")
        try:
            ok, detail = await provider.health()
        finally:
            await provider.aclose()

    assert ok is False
    assert "ollama pull llama3.2" in detail


async def test_ollama_health_passes_when_the_model_is_installed():
    async with RunningServer(build_stub([], installed="llama3.2")) as base:
        provider = OllamaProvider(base_url=base, model="llama3.2")
        try:
            ok, detail = await provider.health()
        finally:
            await provider.aclose()

    assert ok is True
    assert "llama3.2" in detail


async def test_ollama_streams_through_the_openai_endpoint():
    async with RunningServer(build_stub(["local ", "model ", "output"])) as base:
        provider = OllamaProvider(base_url=base, model="llama3.2")
        try:
            answer = await provider.complete([Message("user", "hi")])
        finally:
            await provider.aclose()

    assert answer == "local model output"
