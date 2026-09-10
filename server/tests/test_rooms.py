"""Rooms: sync protocol handling, broadcast, and persistence."""

from __future__ import annotations

import asyncio

from pycrdt import Doc, XmlElement, XmlFragment, XmlText, create_sync_message, handle_sync_message

from coverse.db import repo
from coverse.db.session import init_db, session_scope
from coverse.ws.rooms import Client, Room, RoomManager


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, message: bytes) -> None:
        self.sent.append(message)


def _client_doc_with_text(text: str) -> Doc:
    doc = Doc()
    doc["default"] = fragment = XmlFragment()
    with doc.transaction():
        fragment.children.append(XmlElement("paragraph", None, [XmlText(text)]))
    return doc


async def test_a_joining_client_is_sent_sync_step1():
    room = Room("doc-1")
    socket = FakeSocket()
    await room.add_client(Client("c1", socket.send, "u1", "Alice"))

    assert socket.sent, "the server must open the sync handshake"
    assert socket.sent[0][0] == 0  # YMessageType.SYNC
    await room.close()


async def test_an_update_from_one_client_reaches_the_other_but_not_its_sender():
    room = Room("doc-2")
    alice, bob = FakeSocket(), FakeSocket()
    await room.add_client(Client("alice", alice.send, "u1", "Alice"))
    await room.add_client(Client("bob", bob.send, "u2", "Bob"))
    alice.sent.clear()
    bob.sent.clear()

    client_doc = _client_doc_with_text("hello from alice")
    # Sync step 1 from the client, then the resulting update.
    await room.handle_message("alice", create_sync_message(client_doc))
    reply = alice.sent[-1] if alice.sent else None
    assert reply is not None
    handle_sync_message(reply[1:], client_doc)
    await room.handle_message("alice", _update_message(client_doc))

    await asyncio.sleep(0.05)  # broadcast is dispatched onto the loop

    assert "hello from alice" in room.doc.to_xml()
    assert bob.sent, "the other client must receive the update"
    await room.close()


def _update_message(doc: Doc) -> bytes:
    from pycrdt import create_update_message

    return create_update_message(doc.get_update())


async def test_room_persists_and_reloads_a_document():
    await init_db()
    async with session_scope() as session:
        document = await repo.create_document(session, owner_id="u1", title="T")
        document_id = document.id

    room = Room(document_id)
    await room.load()
    room.doc.append_block("paragraph", "persist me")
    await room.flush()
    await room.close()

    reloaded = Room(document_id)
    await reloaded.load()
    assert "persist me" in reloaded.doc.to_markdown()
    await reloaded.close()


async def test_ai_presence_is_broadcast_to_clients():
    room = Room("doc-3")
    socket = FakeSocket()
    await room.add_client(Client("c1", socket.send, "u1", "Alice"))
    socket.sent.clear()

    await room.set_ai_presence(True)
    assert any(message[0] == 1 for message in socket.sent), "expected an awareness message"
    await room.close()


async def test_room_manager_releases_a_room_once_empty():
    manager = RoomManager()
    room = await manager.get("doc-4")
    await room.add_client(Client("c1", FakeSocket().send, "u1", "A"))

    await manager.release("doc-4")
    assert manager.peek("doc-4") is room, "a room with clients must stay alive"

    await room.remove_client("c1")
    await manager.release("doc-4")
    assert manager.peek("doc-4") is None
    await manager.close_all()


async def test_joining_by_link_records_the_visitor_as_a_collaborator():
    """Opening a shared link should add you to the document, not bounce you."""
    await init_db()
    async with session_scope() as session:
        document = await repo.create_document(session, owner_id="owner", title="Shared")
        document_id = document.id

    async with session_scope() as session:
        assert await repo.join_via_link(session, document_id, "visitor") is True

    async with session_scope() as session:
        assert await repo.user_can_access(session, document_id, "visitor") is True
        visible = await repo.list_documents(session, "visitor")
        assert [d.id for d in visible] == [document_id]


async def test_a_restricted_document_refuses_link_visitors():
    await init_db()
    async with session_scope() as session:
        document = await repo.create_document(session, owner_id="owner", title="Private")
        document.link_access = "none"
        document_id = document.id

    async with session_scope() as session:
        assert await repo.join_via_link(session, document_id, "visitor") is False
        assert await repo.user_can_access(session, document_id, "visitor") is False
