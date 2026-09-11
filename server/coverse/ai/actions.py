"""Running the model and putting its reply into the room.

Two actions, because the room only has two shapes of question: one everybody
sees, and one only the asker sees.

`reply` streams into a message body that already exists in the shared document,
so every member watches it fill in through ordinary CRDT sync. There is no
separate broadcast path for AI output.

`fork_reply` answers one person privately. It never touches shared state, so its
deltas go back over that person's control socket instead.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from ..crdt.room import RoomDoc
from . import prompts
from .base import Message, Provider

# Flush a batch when the buffer ends a sentence, so readers see whole thoughts.
_SENTENCE_ENDINGS = (". ", ".\n", "! ", "? ", ":\n", "\n\n")


class DeltaBatcher:
    """Accumulates streamed text and decides when it is worth a CRDT commit.

    One transaction per token would be a write storm against every connected
    client. Batching on a short timer, or at a sentence boundary, keeps it
    looking live while cutting the update count by roughly an order of magnitude.
    """

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


async def reply(
    *,
    provider: Provider,
    room: RoomDoc,
    flush_ms: int = 50,
    roster: list[str] | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Answer the thread, streaming into the shared document.

    The assistant message is appended first and filled in as tokens arrive, so
    everyone sees an empty bubble appear and then fill, and anyone joining mid
    reply syncs into the correct partial state.
    """
    transcript = room.transcript()
    messages = prompts.build(transcript)
    if roster:
        messages.insert(1, Message("system", prompts.roster_line(roster)))

    message_id, entry = room.add_message(
        role="assistant", author="assistant", author_name="Assistant"
    )
    body = room.message_body(entry)
    batcher = DeltaBatcher(flush_ms)

    yield {"type": "status", "status": "streaming", "message": message_id}

    def commit(chunk: str) -> None:
        with room.doc.transaction():
            body.insert(len(str(body)), chunk)

    try:
        async for delta in provider.stream(messages, **opts):
            if delta.done:
                break
            chunk = batcher.add(delta.text)
            if chunk:
                commit(chunk)
        remaining = batcher.flush()
        if remaining:
            commit(remaining)
    finally:
        # Runs on cancellation too: a stopped reply keeps whatever it had
        # written and is marked finished rather than left spinning forever.
        room.finish_message(entry)

    yield {"type": "done", "message": message_id}


async def fork_reply(
    *,
    provider: Provider,
    room: RoomDoc,
    question: str,
    asker_name: str,
    history: list[dict[str, str]] | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Answer one person privately, with the room's thread as context."""
    transcript = list(room.transcript())
    transcript.extend(history or [])
    transcript.append({"role": "user", "author_name": asker_name, "body": question})

    messages = prompts.build(transcript, fork=True)

    yield {"type": "status", "status": "streaming"}

    parts: list[str] = []
    async for delta in provider.stream(messages, **opts):
        if delta.done:
            break
        parts.append(delta.text)
        yield {"type": "delta", "text": delta.text}

    yield {"type": "done", "answer": "".join(parts).strip()}


async def collect(stream: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drain an action stream. Used by tests."""
    return [event async for event in stream]
