"""A provider that fakes a model, so the product runs with no keys and no network.

This is the default. It streams deterministic, structurally plausible markdown at
a realistic pace, which is enough to build and test the entire CRDT, suggestion
and UI surface against.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from typing import Any

from .base import Delta, Message, Provider, ProviderError

_LOREM = (
    "Collaborative editing works because every change is expressed as an operation "
    "that can be merged without a central arbiter. Each client holds a replica, and "
    "the replicas converge. The interesting part is not the merging itself but what "
    "it lets you build on top: an assistant can hold a replica too, and write into "
    "the document as a peer rather than as a batch job."
)


class MockProvider(Provider):
    name = "mock"

    def __init__(self, delay_ms: int = 25, model: str = "mock-model") -> None:
        self.delay_ms = delay_ms
        self.model = model

    async def stream(self, messages: list[Message], **opts: Any) -> AsyncIterator[Delta]:
        prompt = messages[-1].content if messages else ""

        # An escape hatch for exercising error handling in the UI.
        if "__fail__" in prompt:
            raise ProviderError("mock provider asked to fail", provider=self.name)

        text = self._response_for(prompt, opts.get("action", ""))
        delay = max(self.delay_ms, 0) / 1000

        for token in _tokenize(text):
            if delay:
                await asyncio.sleep(delay)
            yield Delta(text=token)
        yield Delta(done=True, meta={"model": self.model, "provider": self.name})

    def _response_for(self, prompt: str, action: str) -> str:
        """Deterministic per prompt, so tests can assert on output.

        Keyed on the caller's explicit action rather than sniffing the prompt
        text: the real system prompts share too much vocabulary for substring
        matching to be reliable.
        """
        if action == "rewrite":
            original = _extract_quoted(prompt) or "the selected text"
            return f"{original.strip().rstrip('.')}, rewritten for clarity and concision."

        if action == "comment":
            return (
                "This passage buries its main claim in the final clause. "
                "Consider leading with it, and cutting the hedge in the second sentence."
            )

        if action == "ask":
            return (
                "Based on the document, the short answer is yes. The relevant section "
                "sets out the mechanism, though it does not address failure modes."
            )

        seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        topic = _topic_of(prompt)
        heading = _truncate_words(topic, 60).rstrip("?.!").capitalize() or "A section"
        subject = _truncate_words(topic, 34) or "it"
        bullets = "\n".join(f"- Point {i + 1} about {subject}" for i in range(2 + seed % 2))
        return f"## {heading}\n\n{_LOREM}\n\n{bullets}\n\nA closing thought to round it out."

    async def health(self) -> tuple[bool, str]:
        return True, "mock provider is always available"


def _tokenize(text: str) -> list[str]:
    """Split into word-ish tokens, keeping whitespace, like a real token stream."""
    return re.findall(r"\s+|\S+", text)


def _topic_of(prompt: str) -> str:
    """The user's actual instruction, without the document context appended to it.

    Prompts arrive with the current document attached for context. Echoing that
    back would make the mock's output look like it had leaked its own prompt.
    """
    head = prompt.split("Current document:")[0]
    head = head.split("The document is currently empty")[0]
    return " ".join(head.strip().splitlines()).strip()


def _truncate_words(text: str, limit: int) -> str:
    """Cut to `limit` characters without slicing a word in half."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    spaced = cut.rsplit(" ", 1)[0]
    return (spaced or cut).rstrip(",;:")


def _extract_quoted(prompt: str) -> str | None:
    match = re.search(r'"""(.*?)"""', prompt, re.DOTALL) or re.search(r'"(.+?)"', prompt, re.DOTALL)
    return match.group(1) if match else None
