"""The shared state of one room, as a single Yjs document.

Everything the room shows is in here, which means everything the room shows is
synchronized, live, to every member, through one transport. There is no separate
fan-out path and no polling: a spectator seeing the AI type is the same mechanism
as a spectator seeing someone else edit the shared draft.

    messages   Array   the AI thread. A streaming reply's body is a Text, so it
                       fills in live for everyone, and a late joiner syncs into
                       the middle of a half written reply correctly.
    sidechat   Array   the human backchannel. Never sent to the model.
    queue      Array   prompts proposed by anyone; the driver sends or drops them.
    composer   Text    the shared draft everyone can type into.
    pins       Map     starred message ids.
    control    Map     who holds the mic, who has asked for it, what is running.

Messages are Maps rather than plain dicts so that a body can be a live Text and
so reactions can be updated without rewriting the whole entry.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pycrdt import Array, Doc, Map, Text

MESSAGES = "messages"
SIDECHAT = "sidechat"
QUEUE = "queue"
COMPOSER = "composer"
PINS = "pins"
CONTROL = "control"

# control keys
DRIVER = "driver"
DRIVER_NAME = "driver_name"
REQUESTS = "requests"
JOB = "job"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RoomDoc:
    """The server's live replica of one room."""

    def __init__(self, doc: Doc | None = None) -> None:
        self.doc = doc or Doc()
        self.doc[MESSAGES] = Array()
        self.doc[SIDECHAT] = Array()
        self.doc[QUEUE] = Array()
        self.doc[COMPOSER] = Text()
        self.doc[PINS] = Map()
        self.doc[CONTROL] = Map()

    # --- shared types ----------------------------------------------------------

    @property
    def messages(self) -> Array:
        return self.doc[MESSAGES]

    @property
    def sidechat(self) -> Array:
        return self.doc[SIDECHAT]

    @property
    def queue(self) -> Array:
        return self.doc[QUEUE]

    @property
    def composer(self) -> Text:
        return self.doc[COMPOSER]

    @property
    def pins(self) -> Map:
        return self.doc[PINS]

    @property
    def control(self) -> Map:
        return self.doc[CONTROL]

    # --- state transfer --------------------------------------------------------

    def encode_update(self, state: bytes | None = None) -> bytes:
        return self.doc.get_update(state) if state else self.doc.get_update()

    def apply_update(self, update: bytes) -> None:
        self.doc.apply_update(update)

    # --- the mic ---------------------------------------------------------------

    @property
    def driver(self) -> str | None:
        value = self.control.get(DRIVER)
        return str(value) if value else None

    @property
    def driver_name(self) -> str:
        return str(self.control.get(DRIVER_NAME) or "")

    def set_driver(self, member_id: str | None, name: str = "") -> None:
        """Hand the mic over, clearing any request from the new holder.

        The name is stored beside the id because every client needs to render
        "X has the mic", and resolving that from presence would break the moment
        someone's awareness entry has not arrived yet.
        """
        with self.doc.transaction():
            self.control[DRIVER] = member_id or ""
            self.control[DRIVER_NAME] = name if member_id else ""
            if member_id:
                requests = self._requests()
                self.control[REQUESTS] = [r for r in requests if r.get("id") != member_id]

    def _requests(self) -> list[dict[str, Any]]:
        raw = self.control.get(REQUESTS)
        return [dict(r) for r in raw] if raw else []

    def request_mic(self, member_id: str, name: str) -> None:
        with self.doc.transaction():
            requests = self._requests()
            if any(r.get("id") == member_id for r in requests):
                return
            requests.append({"id": member_id, "name": name, "at": time.time()})
            self.control[REQUESTS] = requests

    def withdraw_request(self, member_id: str) -> None:
        with self.doc.transaction():
            self.control[REQUESTS] = [r for r in self._requests() if r.get("id") != member_id]

    @property
    def running_job(self) -> str | None:
        value = self.control.get(JOB)
        return str(value) if value else None

    def set_running_job(self, job_id: str | None) -> None:
        with self.doc.transaction():
            self.control[JOB] = job_id or ""

    # --- the thread ------------------------------------------------------------

    def add_message(
        self,
        *,
        role: str,
        author: str,
        author_name: str,
        body: str = "",
        shared: bool = False,
        done: bool | None = None,
    ) -> tuple[str, Map]:
        """Append a message. The body is a Text so a reply can stream into it.

        ``shared`` marks a message brought in from someone's private thread, so
        the room can see where it came from rather than it looking like it was
        asked out loud.
        """
        message_id = new_id("msg")
        with self.doc.transaction():
            entry = Map(
                {
                    "id": message_id,
                    "role": role,
                    "author": author,
                    "author_name": author_name,
                    "body": Text(body),
                    "at": time.time(),
                    "done": done if done is not None else role != "assistant",
                    "shared": shared,
                    "reactions": Map(),
                }
            )
            self.messages.append(entry)
            return message_id, self.messages[len(self.messages) - 1]

    def message_body(self, entry: Map) -> Text:
        return entry["body"]

    def finish_message(self, entry: Map) -> None:
        with self.doc.transaction():
            entry["done"] = True

    def transcript(self) -> list[dict[str, str]]:
        """The thread as plain data, for building a prompt."""
        out: list[dict[str, str]] = []
        for entry in self.messages:
            out.append(
                {
                    "role": str(entry["role"]),
                    "author_name": str(entry["author_name"]),
                    "body": str(entry["body"]),
                }
            )
        return out

    # --- side chat -------------------------------------------------------------

    def add_sidechat(self, *, author: str, author_name: str, body: str) -> str:
        message_id = new_id("side")
        with self.doc.transaction():
            self.sidechat.append(
                {
                    "id": message_id,
                    "author": author,
                    "author_name": author_name,
                    "body": body,
                    "at": time.time(),
                }
            )
        return message_id

    # --- queue -----------------------------------------------------------------

    def add_to_queue(self, *, author: str, author_name: str, body: str) -> str:
        item_id = new_id("q")
        with self.doc.transaction():
            self.queue.append(
                {
                    "id": item_id,
                    "author": author,
                    "author_name": author_name,
                    "body": body,
                    "at": time.time(),
                }
            )
        return item_id

    def take_from_queue(self, item_id: str) -> dict[str, Any] | None:
        """Remove a queued prompt and return it."""
        with self.doc.transaction():
            for index in range(len(self.queue)):
                item = dict(self.queue[index])
                if item.get("id") == item_id:
                    del self.queue[index]
                    return item
        return None

    # --- pins and reactions ----------------------------------------------------

    def toggle_pin(self, message_id: str, member_id: str) -> bool:
        with self.doc.transaction():
            if message_id in self.pins:
                del self.pins[message_id]
                return False
            self.pins[message_id] = {"by": member_id, "at": time.time()}
            return True

    def toggle_reaction(self, message_id: str, emoji: str, member_id: str) -> None:
        for entry in self.messages:
            if str(entry["id"]) != message_id:
                continue
            with self.doc.transaction():
                reactions = entry["reactions"]
                holders = list(reactions.get(emoji) or [])
                if member_id in holders:
                    holders.remove(member_id)
                else:
                    holders.append(member_id)
                if holders:
                    reactions[emoji] = holders
                elif emoji in reactions:
                    del reactions[emoji]
            return

    # --- composer --------------------------------------------------------------

    def clear_composer(self) -> str:
        """Empty the shared draft, returning what it held."""
        text = str(self.composer)
        if text:
            with self.doc.transaction():
                del self.composer[0 : len(text)]
        return text

    def set_composer(self, value: str) -> None:
        with self.doc.transaction():
            existing = len(str(self.composer))
            if existing:
                del self.composer[0:existing]
            if value:
                self.composer.insert(0, value)
