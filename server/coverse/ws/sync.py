"""The Yjs sync socket: `/ws/room/{code}`.

Pure binary y-websocket protocol. This one socket carries the entire shared
state of the room: the thread, the side chat, the queue, the shared draft, pins
and the baton. Anything a member sees another member do arrives here.

Membership is the only access check. You get a member id by joining over HTTP
first, which is where the room password is enforced.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .rooms import Client, registry

logger = logging.getLogger(__name__)
router = APIRouter()

WS_UNAUTHORIZED = 4401
WS_NOT_FOUND = 4404


@router.websocket("/ws/room/{code}")
async def room_socket(websocket: WebSocket, code: str, member: str = Query(default="")) -> None:
    room = registry.get(code)
    if room is None:
        await websocket.accept()
        await websocket.close(code=WS_NOT_FOUND, reason="no such room")
        return

    if not member or room.get_member(member) is None:
        # Accept first so the browser receives the close code rather than an
        # opaque handshake failure.
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED, reason="join the room first")
        return

    await websocket.accept()

    client_id = uuid.uuid4().hex
    client = Client(client_id, websocket.send_bytes, member)
    await room.add_client(client)
    logger.info("%s joined %s (%d online)", member[:8], room.code, len(room.roster()))

    try:
        while True:
            message = await websocket.receive_bytes()
            await room.handle_message(client_id, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("sync socket error in room %s", code)
    finally:
        await room.remove_client(client_id)
