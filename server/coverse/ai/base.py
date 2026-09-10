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

    async def aclose(self) -> None:
        return None
