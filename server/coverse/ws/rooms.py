"""Rooms: one live replica of the shared state, plus who is in it.

Rooms are ephemeral and live only in memory. There is no database, no accounts
and nothing written to disk, so closing the last tab really does end the room.

Two deliberate grace periods stop that from being hostile:

* An empty room is kept for a short while before it is dropped, because a page
  refresh disconnects everyone momentarily and it would be absurd for reloading
  to destroy the session.
* A driver who disconnects keeps the mic for a few seconds, then it is released
  automatically. Otherwise one dropped laptop blocks the whole room with no way
  to recover.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import secrets
import time
from collections.abc import Awaitable, Callable

from pycrdt import (
    Awareness,
    YMessageType,
    create_awareness_message,
    create_sync_message,
    create_update_message,
    handle_sync_message,
    read_message,
)

from ..config import get_settings
from ..crdt.room import RoomDoc

logger = logging.getLogger(__name__)

Sender = Callable[[bytes], Awaitable[None]]

# Ambiguous characters are left out so a code can be read aloud across a table.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


class Member:
    """One person in the room. Identity lasts only as long as the room does."""

    __slots__ = ("id", "name", "color", "sprite", "joined_at", "connections")

    def __init__(self, member_id: str, name: str, color: str, sprite: str = "") -> None:
        self.id = member_id
        self.name = name
        self.color = color
        self.sprite = sprite
        self.joined_at = time.time()
        # A member can have more than one socket open (the sync socket and the
        # control socket, or two tabs), so presence is a count, not a flag.
        self.connections = 0

    @property
    def online(self) -> bool:
        return self.connections > 0


class Client:
    """One connected sync socket."""

    __slots__ = ("id", "send", "member_id")

    def __init__(self, client_id: str, send: Sender, member_id: str) -> None:
        self.id = client_id
        self.send = send
        self.member_id = member_id


class Room:
    def __init__(self, code: str, password: str = "") -> None:
        self.code = code
        self.password_hash = hash_password(password) if password else ""
        self.state = RoomDoc()
        self.awareness = Awareness(self.state.doc)
        self.members: dict[str, Member] = {}
        self.clients: dict[str, Client] = {}
        self.created_at = time.time()
        self.empty_since: float | None = time.time()

        self._settings = get_settings()
        self.state.set_model(self._settings.resolved_model)
        self._current_origin: str | None = None
        self._driver_grace: asyncio.Task[None] | None = None
        self._subscription = self.state.doc.observe(self._on_update)

    # --- access ----------------------------------------------------------------

    @property
    def needs_password(self) -> bool:
        return bool(self.password_hash)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return True
        return secrets.compare_digest(self.password_hash, hash_password(password or ""))

    # --- membership ------------------------------------------------------------

    def add_member(self, name: str, color: str, sprite: str = "") -> Member:
        member = Member(secrets.token_hex(8), name.strip()[:40] or "Anonymous", color, sprite)
        self.members[member.id] = member
        # Mirror into shared state so every client can draw this person, even
        # after they disconnect and drop out of awareness.
        self.state.put_member(member.id, name=member.name, color=member.color, sprite=member.sprite)
        # First person through the door takes the mic, so a solo user never has
        # to ask themselves for permission to type.
        if self.state.driver is None or self.state.driver == "":
            self.state.set_driver(member.id, member.name)
        return member

    def get_member(self, member_id: str) -> Member | None:
        return self.members.get(member_id)

    def roster(self) -> list[str]:
        return [m.name for m in self.members.values() if m.online]

    def connect(self, member_id: str) -> None:
        member = self.members.get(member_id)
        if member:
            member.connections += 1
        self.empty_since = None
        if self._driver_grace and not self._driver_grace.done():
            self._driver_grace.cancel()
            self._driver_grace = None

    def disconnect(self, member_id: str) -> None:
        member = self.members.get(member_id)
        if member:
            member.connections = max(0, member.connections - 1)
        if not any(m.online for m in self.members.values()):
            self.empty_since = time.time()
        if self.state.driver == member_id and member and not member.online:
            self._schedule_driver_release(member_id)

    def _schedule_driver_release(self, member_id: str) -> None:
        """Release the mic if a disconnected driver does not come back."""
        if self._driver_grace and not self._driver_grace.done():
            return

        async def release() -> None:
            await asyncio.sleep(self._settings.driver_grace_seconds)
            member = self.members.get(member_id)
            if member and member.online:
                return  # they reconnected, keep the mic where it was
            if self.state.driver != member_id:
                return
            self.members.pop(member_id, None)
            self._hand_to(self._next_driver())
            logger.info("released mic in %s from absent driver", self.code)

        with contextlib.suppress(RuntimeError):
            self._driver_grace = asyncio.get_running_loop().create_task(release())

    def _hand_to(self, member_id: str | None) -> None:
        member = self.members.get(member_id) if member_id else None
        self.state.set_driver(member_id, member.name if member else "")

    def _next_driver(self) -> str | None:
        """Longest present member still online, or nobody."""
        online = sorted((m for m in self.members.values() if m.online), key=lambda m: m.joined_at)
        return online[0].id if online else None

    @property
    def is_empty(self) -> bool:
        return not any(m.online for m in self.members.values())

    # --- mic --------------------------------------------------------------------

    def is_driver(self, member_id: str) -> bool:
        return self.state.driver == member_id

    def grant_mic(self, granter_id: str, target_id: str) -> bool:
        """Only the current driver can hand the mic on."""
        if not self.is_driver(granter_id):
            return False
        if target_id not in self.members:
            return False
        self._hand_to(target_id)
        return True

    def release_mic(self, member_id: str) -> bool:
        if not self.is_driver(member_id):
            return False
        self._hand_to(self._next_driver())
        return True

    # --- sync protocol ----------------------------------------------------------

    async def add_client(self, client: Client) -> None:
        self.clients[client.id] = client
        self.connect(client.member_id)
        await client.send(create_sync_message(self.state.doc))
        await self._send_awareness_to(client)

    async def remove_client(self, client_id: str) -> None:
        client = self.clients.pop(client_id, None)
        if client:
            self.disconnect(client.member_id)

    async def handle_message(self, client_id: str, message: bytes) -> None:
        if not message:
            return

        message_type = message[0]
        payload = message[1:]

        if message_type == YMessageType.SYNC:
            self._current_origin = client_id
            try:
                reply = handle_sync_message(payload, self.state.doc)
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
            await self.broadcast(create_awareness_message(update), exclude=client_id)

    def _on_update(self, event: object) -> None:
        update = event.update  # type: ignore[attr-defined]
        message = create_update_message(update)
        origin = self._current_origin
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(message, exclude=origin))

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
            await self.remove_client(client_id)

    async def _send_awareness_to(self, client: Client) -> None:
        states = self.awareness.states
        if not states:
            return
        with contextlib.suppress(Exception):
            update = self.awareness.encode_awareness_update(list(states.keys()))
            await client.send(create_awareness_message(update))

    async def set_ai_presence(self, active: bool) -> None:
        """Show the assistant in the roster while it is generating."""
        state = (
            {"user": {"name": "Assistant", "color": "#8b5cf6", "isAI": True}} if active else None
        )
        try:
            self.awareness.set_local_state(state)
            update = self.awareness.encode_awareness_update([self.awareness.client_id])
        except Exception:
            return
        await self.broadcast(create_awareness_message(update))

    async def close(self) -> None:
        if self._driver_grace and not self._driver_grace.done():
            self._driver_grace.cancel()
        with contextlib.suppress(Exception):
            self._subscription.drop()


class RoomRegistry:
    """All live rooms in the process."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task[None] | None = None

    async def create(self, password: str = "") -> Room:
        async with self._lock:
            code = generate_code()
            while code in self._rooms:
                code = generate_code()
            room = Room(code, password)
            self._rooms[code] = room
            logger.info("created room %s", code)
            return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get(code.upper())

    def exists(self, code: str) -> bool:
        return code.upper() in self._rooms

    async def start_reaper(self) -> None:
        if self._reaper and not self._reaper.done():
            return
        self._reaper = asyncio.create_task(self._reap_forever())

    async def _reap_forever(self) -> None:
        """Drop rooms that have stood empty past the grace period."""
        settings = get_settings()
        while True:
            await asyncio.sleep(30)
            cutoff = time.time() - settings.room_grace_seconds
            async with self._lock:
                doomed = [
                    code
                    for code, room in self._rooms.items()
                    if room.is_empty and room.empty_since and room.empty_since < cutoff
                ]
                rooms = [self._rooms.pop(code) for code in doomed]
            for room in rooms:
                await room.close()
            if doomed:
                logger.info("reaped empty rooms: %s", ", ".join(doomed))

    async def close_all(self) -> None:
        async with self._lock:
            rooms = list(self._rooms.values())
            self._rooms.clear()
        if self._reaper and not self._reaper.done():
            self._reaper.cancel()
        for room in rooms:
            await room.close()

    @property
    def active(self) -> dict[str, int]:
        return {code: len(room.roster()) for code, room in self._rooms.items()}


registry = RoomRegistry()
