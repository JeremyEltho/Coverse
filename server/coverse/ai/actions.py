"""Orchestration: run a model, turn its output into document changes.

Each action is an async generator of JSON-serializable events for the chat/control
socket. Document mutations happen as a side effect, on the server's live CRDT
replica, and reach clients through the sync socket instead of through these events.

Two things every action gets right:

* **Batching.** Committing one CRDT transaction per token is a write storm, so
  deltas accumulate and flush on a timer or at a sentence boundary.
* **Cancellation.** Each action runs as an `asyncio.Task`; cancelling it leaves
  already-committed text in place rather than trying to roll back, which is what
  a human collaborator being interrupted mid-sentence would look like.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from ..crdt import suggestions as suggestion_store
from ..crdt.document import CoverseDoc
from ..crdt.edits import StreamTarget, rewrite_document
from ..crdt.positions import TextAnchor
from . import prompts
from .base import Delta, Message, Provider, ProviderError

# Flush a batch when the buffer ends a sentence, so readers see whole thoughts.
_SENTENCE_ENDINGS = (". ", ".\n", "! ", "? ", ":\n", "\n\n")


class DeltaBatcher:
    """Accumulates streamed text and decides when it is worth a CRDT commit."""

    def __init__(self, flush_ms: int = 50) -> None:
        self.flush_seconds = max(flush_ms, 0) / 1000
        self._buffer: list[str] = []
        self._last_flush = time.monotonic()

    def add(self, text: str) -> str | None:
        self._buffer.append(text)
        joined = "".join(self._buffer)

        due = (time.monotonic() - self._last_flush) >= self.flush_seconds
        boundary = any(joined.endswith(end) for end in _SENTENCE_ENDINGS)

        if due or boundary:
            return self.flush()
        return None

    def flush(self) -> str | None:
        if not self._buffer:
            return None
        joined = "".join(self._buffer)
        self._buffer.clear()
        self._last_flush = time.monotonic()
        return joined


async def generate(
    *,
    provider: Provider,
    doc: CoverseDoc,
    instruction: str,
    author: str,
    flush_ms: int = 50,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Stream new content directly into the document, visible live to everyone."""
    messages = [
        Message("system", prompts.GENERATE),
        Message("user", prompts.with_document_context(instruction, doc.to_markdown())),
    ]

    target = StreamTarget.append_to(doc)
    batcher = DeltaBatcher(flush_ms)
    opts.setdefault("action", "generate")
    yield {"type": "status", "status": "streaming", "action": "generate"}

    try:
        async for delta in provider.stream(messages, **opts):
            if delta.done:
                break
            chunk = batcher.add(delta.text)
            if chunk:
                target.append(chunk)
                yield {"type": "delta", "text": chunk}
        remaining = batcher.flush()
        if remaining:
            target.append(remaining)
            yield {"type": "delta", "text": remaining}
    finally:
        # Runs on cancellation too, so a half-written block is still tidy.
        target.finish()

    yield {"type": "done", "action": "generate", "written": target.written}


async def rewrite(
    *,
    provider: Provider,
    doc: CoverseDoc,
    selection: str,
    instruction: str,
    author: str,
    relpos: dict[str, str] | None = None,
    anchor: dict[str, Any] | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Propose a replacement for a selected passage, as a pending suggestion.

    Nothing in the document body changes here. The suggestion lands in the shared
    suggestions Map, every client sees it, and a human accepts or rejects it.
    """
    messages = [
        Message("system", prompts.REWRITE),
        Message("user", prompts.rewrite_prompt(selection, instruction)),
    ]

    opts.setdefault("action", "rewrite")
    yield {"type": "status", "status": "streaming", "action": "rewrite"}

    parts: list[str] = []
    async for delta in provider.stream(messages, **opts):
        if delta.done:
            break
        parts.append(delta.text)
        yield {"type": "delta", "text": delta.text}

    replacement = "".join(parts).strip()
    if not replacement:
        raise ProviderError("model returned an empty rewrite")

    suggestion_id = suggestion_store.create(
        doc.suggestions,
        kind="rewrite",
        original=selection,
        replacement=replacement,
        author=author,
        relpos=relpos,
        anchor=anchor or TextAnchor(text=selection, offset=0).to_json(),
    )

    yield {
        "type": "suggestion",
        "action": "rewrite",
        "id": suggestion_id,
        "replacement": replacement,
    }
    yield {"type": "done", "action": "rewrite", "id": suggestion_id}


async def comment(
    *,
    provider: Provider,
    doc: CoverseDoc,
    selection: str,
    author: str,
    relpos: dict[str, str] | None = None,
    anchor: dict[str, Any] | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Leave a margin note on a passage. Never edits the document."""
    messages = [
        Message("system", prompts.COMMENT),
        Message("user", prompts.comment_prompt(selection, doc.to_markdown())),
    ]

    opts.setdefault("action", "comment")
    yield {"type": "status", "status": "streaming", "action": "comment"}

    parts: list[str] = []
    async for delta in provider.stream(messages, **opts):
        if delta.done:
            break
        parts.append(delta.text)
        yield {"type": "delta", "text": delta.text}

    body = "".join(parts).strip()
    if not body:
        raise ProviderError("model returned an empty comment")

    suggestion_id = suggestion_store.create(
        doc.suggestions,
        kind="comment",
        original=selection,
        body=body,
        author=author,
        relpos=relpos,
        anchor=anchor or TextAnchor(text=selection, offset=0).to_json(),
    )

    yield {"type": "suggestion", "action": "comment", "id": suggestion_id, "body": body}
    yield {"type": "done", "action": "comment", "id": suggestion_id}


async def ask(
    *,
    provider: Provider,
    doc: CoverseDoc,
    question: str,
    history: list[Message] | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Answer a question about the document. Streams to chat only, no edits."""
    messages: list[Message] = [Message("system", prompts.ASK)]
    messages.extend(history or [])
    messages.append(Message("user", prompts.with_document_context(question, doc.to_markdown())))

    opts.setdefault("action", "ask")
    yield {"type": "status", "status": "streaming", "action": "ask"}

    parts: list[str] = []
    async for delta in provider.stream(messages, **opts):
        if delta.done:
            break
        parts.append(delta.text)
        yield {"type": "delta", "text": delta.text}

    yield {"type": "done", "action": "ask", "answer": "".join(parts).strip()}


async def canvas(
    *,
    provider: Provider,
    doc: CoverseDoc,
    instruction: str,
    history: list[Message] | None = None,
    flush_ms: int = 50,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Canvas mode: rebuild the document from the conversation.

    The model returns the whole document, so the result is buffered and applied as
    one transaction at the end -- streaming a full-document rewrite into the CRDT
    would make the doc flicker through every intermediate state for every viewer.
    The tokens still stream to the chat pane so it feels live.
    """
    messages: list[Message] = [Message("system", prompts.CANVAS)]
    messages.extend(history or [])
    messages.append(Message("user", prompts.with_document_context(instruction, doc.to_markdown())))

    opts.setdefault("action", "canvas")
    yield {"type": "status", "status": "streaming", "action": "canvas"}

    parts: list[str] = []
    async for delta in provider.stream(messages, **opts):
        if delta.done:
            break
        parts.append(delta.text)
        yield {"type": "delta", "text": delta.text}

    markdown = "".join(parts).strip()
    if markdown:
        rewrite_document(doc, markdown)

    yield {"type": "done", "action": "canvas", "length": len(markdown)}


async def collect(stream: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drain an action stream. Used by tests."""
    return [event async for event in stream]


__all__ = ["generate", "rewrite", "comment", "ask", "canvas", "DeltaBatcher", "Delta", "collect"]
