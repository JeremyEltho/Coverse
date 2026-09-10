"""The Yjs sync socket: `/ws/doc/{document_id}`.

Pure binary y-websocket protocol -- document updates and awareness, nothing else.
Application-level messages go on the chat socket instead, which keeps this one a
faithful Yjs transport that the stock browser client can talk to unmodified.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..auth import WS_FORBIDDEN, WS_UNAUTHORIZED, user_from_ws_token
from ..config import get_settings
from ..db import repo
from ..db.session import session_scope
from .rooms import Client, room_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/doc/{document_id}")
async def document_socket(
    websocket: WebSocket, document_id: str, token: str = Query(default="")
) -> None:
    settings = get_settings()

    user = user_from_ws_token(token, settings)
    if user is None:
        # Accept first so the client receives the close code rather than a bare
        # handshake failure, which browsers surface as an opaque error.
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED, reason="invalid or missing token")
        return

    if not await _can_access(document_id, user.id, settings.auth_required):
        await websocket.accept()
        await websocket.close(code=WS_FORBIDDEN, reason="no access to this document")
        return

    await websocket.accept()

    room = await room_manager.get(document_id)
    client_id = uuid.uuid4().hex
    client = Client(client_id, websocket.send_bytes, user.id, user.display_name)
    await room.add_client(client)
    logger.info("client %s joined %s (%d in room)", user.id, document_id, len(room.clients))

    try:
        while True:
            message = await websocket.receive_bytes()
            await room.handle_message(client_id, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("sync socket error on %s", document_id)
    finally:
        await room.remove_client(client_id)
        await room_manager.release(document_id)
        logger.info("client %s left %s", user.id, document_id)


async def _can_access(document_id: str, user_id: str, auth_required: bool) -> bool:
    """Authorize a document connection.

    When auth is off, connecting to an id that does not exist yet creates it, so
    opening a fresh URL and typing just works. Creating the row (rather than
    waving the connection through) keeps the REST endpoints consistent with the
    socket: the document shows up in listings and its content is fetchable.
    """
    async with session_scope() as session:
        document = await repo.get_document(session, document_id)
        if document is not None:
            # Opening someone's link joins the document, rather than bouncing.
            return await repo.join_via_link(session, document_id, user_id)

        if auth_required:
            return False

        await repo.create_document_with_id(session, document_id=document_id, owner_id=user_id)
        logger.info("auto-created document %s for %s", document_id, user_id)
        return True
