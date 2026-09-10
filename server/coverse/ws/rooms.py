"""Rooms: one live CRDT replica per document, shared by every connected client.

A room owns a `CoverseDoc`, the set of connected sockets, the awareness state, and
the debounced write-back to the database. The server is a real Yjs peer here, not
a relay: it applies every update to its own replica, which is exactly what lets
the AI edit the document as a participant.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pycrdt import (
    Awareness,
    YMessageType,
    create_awareness_message,
    create_sync_message,
    create_update_message,
    handle_sync_message,
    merge_updates,
    read_message,
)

from ..config import get_settings
from ..crdt.document import CoverseDoc
from ..db import repo
from ..db.session import session_scope

logger = logging.getLogger(__name__)

# Sender is an async callable that puts bytes on one client's socket.
Sender = Callable[[bytes], Awaitable[None]]


class Client:
    """One connected websocket in a room."""

    __slots__ = ("id", "send", "user_id", "name")

    def __init__(self, client_id: str, send: Sender, user_id: str, name: str) -> None:
        self.id = client_id
        self.send = send
        self.user_id = user_id
        self.name = name


class Room:
    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        self.doc = CoverseDoc()
        self.awareness = Awareness(self.doc.doc)
        self.clients: dict[str, Client] = {}

        self._settings = get_settings()
        self._loaded = False
        self._lock = asyncio.Lock()

        # Updates produced since the last database write.
        self._pending: list[bytes] = []
        self._flush_task: asyncio.Task[None] | None = None
        self._first_pending_at: float | None = None

        # Set while applying an incoming update, so it is not echoed to its sender.
        self._current_origin: str | None = None

        self._subscription = self.doc.doc.observe(self._on_doc_update)

    # --- lifecycle -------------------------------------------------------------

    async def load(self) -> None:
        """Rebuild the document from its persisted update log, once."""
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            try:
                async with session_scope() as session:
                    updates = await repo.load_updates(session, self.document_id)
                for update in updates:
                    self.doc.apply_update(update)
                # Replaying our own history would otherwise queue it straight back
                # up for writing.
                self._pending.clear()
                self._first_pending_at = None
                logger.info("loaded document %s from %d updates", self.document_id, len(updates))
            except Exception:
                logger.exception("failed to load document %s", self.document_id)
            self._loaded = True

    async def close(self) -> None:
        await self.flush()
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
        with contextlib.suppress(Exception):
            self._subscription.drop()

    @property
    def is_empty(self) -> bool:
        return not self.clients

    # --- client management -----------------------------------------------------

    async def add_client(self, client: Client) -> None:
        self.clients[client.id] = client
        # Step 1 of the sync protocol: tell the newcomer our state so it can
        # send back whatever we are missing.
        await client.send(create_sync_message(self.doc.doc))
        await self._send_awareness_to(client)

    async def remove_client(self, client_id: str) -> None:
        self.clients.pop(client_id, None)
        if not self.clients:
            await self.flush()

    # --- protocol --------------------------------------------------------------

    async def handle_message(self, client_id: str, message: bytes) -> None:
        """Process one y-websocket frame from a client."""
        if not message:
            return

        message_type = message[0]
        payload = message[1:]

        if message_type == YMessageType.SYNC:
            # Tag the origin so the resulting update is not echoed back.
            self._current_origin = client_id
            try:
                reply = handle_sync_message(payload, self.doc.doc)
            finally:
                self._current_origin = None
            if reply is not None:
                client = self.clients.get(client_id)
                if client:
                    await client.send(reply)

        elif message_type == YMessageType.AWARENESS:
            update = read_message(payload)
            with contextlib.suppress(Exception):
                self.awareness.apply_awareness_update(update, "remote")
            # Awareness is ephemeral presence: relay verbatim to everyone else.
            await self.broadcast(create_awareness_message(update), exclude=client_id)

    def _on_doc_update(self, event: Any) -> None:
        """Called by pycrdt for every transaction, local or remote."""
        update = event.update
        self._pending.append(update)
        if self._first_pending_at is None:
            self._first_pending_at = time.monotonic()

        origin = self._current_origin
        message = create_update_message(update)

        # Observers are synchronous; hand the IO to the event loop.
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(message, exclude=origin))
            self._schedule_flush(loop)

    async def broadcast(self, message: bytes, exclude: str | None = None) -> None:
        dead: list[str] = []
        for client_id, client in list(self.clients.items()):
            if client_id == exclude:
                continue
            try:
                await client.send(message)
            except Exception:
                dead.append(client_id)
        for client_id in dead:
            self.clients.pop(client_id, None)

    async def _send_awareness_to(self, client: Client) -> None:
        states = self.awareness.states
        if not states:
            return
        with contextlib.suppress(Exception):
            update = self.awareness.encode_awareness_update(list(states.keys()))
            await client.send(create_awareness_message(update))

    # --- AI presence -----------------------------------------------------------

    async def set_ai_presence(self, active: bool, label: str = "AI") -> None:
        """Publish (or clear) the AI's awareness entry.

        This is what makes an AI cursor appear alongside the humans while the
        model writes.
        """
        state = {"user": {"name": label, "color": "#8b5cf6", "isAI": True}} if active else None
        try:
            self.awareness.set_local_state(state)
            update = self.awareness.encode_awareness_update([self.awareness.client_id])
        except Exception:
            # Awareness is best-effort; never fail an edit over presence.
            return
        await self.broadcast(create_awareness_message(update))

    # --- persistence -----------------------------------------------------------

    def _schedule_flush(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._flush_task and not self._flush_task.done():
            return
        self._flush_task = loop.create_task(self._flush_after_debounce())

    async def _flush_after_debounce(self) -> None:
        """Write back once edits go quiet, or once we have waited long enough.

        Someone typing continuously would otherwise postpone the write forever,
        so `persist_max_wait_ms` forces a flush regardless of idleness.
        """
        debounce = self._settings.persist_debounce_ms / 1000
        max_wait = self._settings.persist_max_wait_ms / 1000

        while self._pending:
            pending_before = len(self._pending)
            await asyncio.sleep(debounce)

            waited = (
                time.monotonic() - self._first_pending_at
                if self._first_pending_at is not None
                else 0.0
            )
            went_idle = len(self._pending) == pending_before

            if went_idle or waited >= max_wait:
                await self.flush()
                return

    async def flush(self) -> None:
        """Persist buffered updates as one merged row."""
        if not self._pending:
            return
        pending, self._pending = self._pending, []
        self._first_pending_at = None

        try:
            merged = merge_updates(*pending) if len(pending) > 1 else pending[0]
            async with session_scope() as session:
                await repo.append_update(session, self.document_id, merged)
                count = await repo.count_updates(session, self.document_id)
                if count > self._settings.compact_after_updates:
                    removed = await repo.compact_updates(session, self.document_id)
                    logger.info("compacted %s, removed %d rows", self.document_id, removed)
        except Exception:
            logger.exception("failed to persist updates for %s", self.document_id)
            # Put them back so the next flush retries rather than losing edits.
            self._pending = pending + self._pending


class RoomManager:
    """Process-wide registry of live rooms."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = asyncio.Lock()

    async def get(self, document_id: str) -> Room:
        async with self._lock:
            room = self._rooms.get(document_id)
            if room is None:
                room = Room(document_id)
                self._rooms[document_id] = room
        await room.load()
        return room

    def peek(self, document_id: str) -> Room | None:
        return self._rooms.get(document_id)

    async def release(self, document_id: str) -> None:
        """Drop a room once its last client leaves."""
        async with self._lock:
            room = self._rooms.get(document_id)
            if room is None or not room.is_empty:
                return
            self._rooms.pop(document_id, None)
        await room.close()

    async def close_all(self) -> None:
        async with self._lock:
            rooms = list(self._rooms.values())
            self._rooms.clear()
        for room in rooms:
            await room.close()

    @property
    def active(self) -> dict[str, int]:
        return {doc_id: len(room.clients) for doc_id, room in self._rooms.items()}


room_manager = RoomManager()
