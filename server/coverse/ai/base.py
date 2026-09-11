"""The provider interface every model backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str

    def to_openai(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ModelInfo:
    """One model a provider can be pointed at."""

    id: str
    name: str
    context_length: int | None = None
    # Price per million tokens, when the provider publishes it. None means the
    # provider does not charge per token (a local model) or did not say.
    prompt_price: float | None = None
    completion_price: float | None = None

    @property
    def is_free(self) -> bool:
        return (self.prompt_price or 0) == 0 and (self.completion_price or 0) == 0

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "context_length": self.context_length,
            "prompt_price": self.prompt_price,
            "completion_price": self.completion_price,
            "free": self.is_free,
        }


@dataclass
class Delta:
    """One chunk of a streamed completion."""

    text: str = ""
    done: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """A provider failed in a way worth showing the user."""

    def __init__(self, message: str, *, provider: str = "", retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class Provider(ABC):
    """Streams completions. Implementations must be cancellation-safe.

    Callers cancel by cancelling the surrounding `asyncio.Task`, so any network
    client held here has to be closed from a `finally` block.
    """

    name: str = "provider"

    @abstractmethod
    def stream(self, messages: list[Message], **opts: Any) -> AsyncIterator[Delta]:
        """Yield `Delta`s until the completion ends."""
        raise NotImplementedError

    async def complete(self, messages: list[Message], **opts: Any) -> str:
        """Collect a full response. Convenience over `stream`."""
        parts: list[str] = []
        async for delta in self.stream(messages, **opts):
            parts.append(delta.text)
        return "".join(parts)

    async def health(self) -> tuple[bool, str]:
        """Report whether the backend is reachable, for the /health endpoint."""
        return True, "ok"

    async def list_models(self) -> list[ModelInfo]:
        """Models this backend can be switched to.

        Returning an empty list means "not switchable", which is what the UI
        uses to decide whether to offer a picker at all.
        """
        return []

    async def aclose(self) -> None:
        return None
