"""The chat and control socket: `/ws/chat/{document_id}`.

Carries JSON: chat turns, AI action requests, streamed tokens for the chat pane,
and job status. Document mutations caused by these actions do not travel on this
socket -- they are applied to the room's CRDT replica and reach clients through
the sync socket.

Client -> server:
    {"type": "generate", "job": "...", "prompt": "..."}
    {"type": "canvas",   "job": "...", "prompt": "..."}
    {"type": "ask",      "job": "...", "prompt": "..."}
    {"type": "rewrite",  "job": "...", "selection": "...", "instruction": "...",
                          "relpos": {...}, "anchor": {...}}
    {"type": "comment",  "job": "...", "selection": "...", "relpos": {...}}
    {"type": "cancel",   "job": "..."}
    {"type": "ping"}

Server -> client:
    {"type": "status"|"delta"|"suggestion"|"done"|"error", "job": "...", ...}
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..ai import actions
from ..ai.base import Message, ProviderError
from ..ai.registry import get_provider
from ..auth import WS_FORBIDDEN, WS_UNAUTHORIZED, user_from_ws_token
from ..config import get_settings
from ..db import repo
from ..db.session import session_scope
from .rooms import Room, room_manager
from .sync import _can_access

logger = logging.getLogger(__name__)
router = APIRouter()

ACTION_TYPES = {"generate", "canvas", "ask", "rewrite", "comment"}


@router.websocket("/ws/chat/{document_id}")
async def chat_socket(
    websocket: WebSocket, document_id: str, token: str = Query(default="")
) -> None:
    settings = get_settings()

    user = user_from_ws_token(token, settings)
    if user is None:
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED, reason="invalid or missing token")
        return

    if not await _can_access(document_id, user.id, settings.auth_required):
        await websocket.accept()
        await websocket.close(code=WS_FORBIDDEN, reason="no access to this document")
        return

    await websocket.accept()
    room = await room_manager.get(document_id)

    # One task per in-flight job, so any of them can be cancelled individually.
    jobs: dict[str, asyncio.Task[None]] = {}

    await websocket.send_json(
        {
            "type": "ready",
            "provider": settings.ai_provider,
            "model": settings.resolved_model,
            "history": await _load_history(document_id),
        }
    )

    try:
        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")

            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if message_type == "cancel":
                job_id = str(payload.get("job", ""))
                task = jobs.get(job_id)
                if task and not task.done():
                    task.cancel()
                continue

            if message_type not in ACTION_TYPES:
                await websocket.send_json(
                    {"type": "error", "error": f"unknown message type: {message_type}"}
                )
                continue

            job_id = str(payload.get("job") or uuid.uuid4().hex)
            task = asyncio.create_task(
                _run_action(
                    websocket=websocket,
                    room=room,
                    document_id=document_id,
                    user_id=user.id,
                    job_id=job_id,
                    payload=payload,
                )
            )
            jobs[job_id] = task

            def _forget(_task: asyncio.Task[None], finished: str = job_id) -> None:
                jobs.pop(finished, None)

            task.add_done_callback(_forget)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("chat socket error on %s", document_id)
    finally:
        # Disconnecting cancels whatever the model was doing for this client.
        for task in jobs.values():
            if not task.done():
                task.cancel()
        for task in list(jobs.values()):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await room_manager.release(document_id)


async def _run_action(
    *,
    websocket: WebSocket,
    room: Room,
    document_id: str,
    user_id: str,
    job_id: str,
    payload: dict[str, Any],
) -> None:
    settings = get_settings()
    provider = get_provider()
    action = payload["type"]
    prompt = str(payload.get("prompt") or "")
    selection = str(payload.get("selection") or "")

    # Only the actions that write to the document should raise an AI cursor.
    shows_presence = action in ("generate", "canvas")

    try:
        if shows_presence:
            await room.set_ai_presence(True)

        if action in ("generate", "canvas", "ask") and prompt:
            async with session_scope() as session:
                await repo.append_chat_message(
                    session,
                    document_id=document_id,
                    user_id=user_id,
                    role="user",
                    content=prompt,
                )

        stream = _build_stream(
            action=action,
            provider=provider,
            room=room,
            payload=payload,
            prompt=prompt,
            selection=selection,
            user_id=user_id,
            flush_ms=settings.stream_flush_ms,
        )

        collected: list[str] = []
        async for event in stream:
            if event.get("type") == "delta":
                collected.append(event.get("text", ""))
            await websocket.send_json({**event, "job": job_id})

        answer = "".join(collected).strip()
        if answer and action in ("generate", "canvas", "ask"):
            async with session_scope() as session:
                await repo.append_chat_message(
                    session,
                    document_id=document_id,
                    user_id=user_id,
                    role="assistant",
                    content=answer,
                    provider=settings.ai_provider,
                    model=settings.resolved_model,
                )

    except asyncio.CancelledError:
        # Whatever was already written stays; that is what interrupting a
        # collaborator mid-sentence looks like.
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "cancelled", "job": job_id, "action": action})
        raise
    except ProviderError as exc:
        logger.warning("provider error on %s: %s", document_id, exc)
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"type": "error", "job": job_id, "error": str(exc), "retryable": exc.retryable}
            )
    except Exception as exc:
        logger.exception("action %s failed on %s", action, document_id)
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"type": "error", "job": job_id, "error": f"{type(exc).__name__}: {exc}"}
            )
    finally:
        if shows_presence:
            with contextlib.suppress(Exception):
                await room.set_ai_presence(False)


def _build_stream(
    *,
    action: str,
    provider: Any,
    room: Room,
    payload: dict[str, Any],
    prompt: str,
    selection: str,
    user_id: str,
    flush_ms: int,
) -> AsyncIterator[dict[str, Any]]:
    doc = room.doc

    if action == "generate":
        return actions.generate(
            provider=provider, doc=doc, instruction=prompt, author=user_id, flush_ms=flush_ms
        )
    if action == "canvas":
        return actions.canvas(
            provider=provider,
            doc=doc,
            instruction=prompt,
            history=_history_messages(payload),
            flush_ms=flush_ms,
        )
    if action == "ask":
        return actions.ask(
            provider=provider, doc=doc, question=prompt, history=_history_messages(payload)
        )
    if action == "rewrite":
        return actions.rewrite(
            provider=provider,
            doc=doc,
            selection=selection,
            instruction=str(payload.get("instruction") or ""),
            author=user_id,
            relpos=payload.get("relpos"),
            anchor=payload.get("anchor"),
        )
    if action == "comment":
        return actions.comment(
            provider=provider,
            doc=doc,
            selection=selection,
            author=user_id,
            relpos=payload.get("relpos"),
            anchor=payload.get("anchor"),
        )
    raise ValueError(f"unsupported action: {action}")


def _history_messages(payload: dict[str, Any]) -> list[Message]:
    """Turn client-supplied conversation history into provider messages."""
    history = payload.get("history") or []
    messages: list[Message] = []
    for entry in history[-20:]:
        role = entry.get("role")
        content = entry.get("content")
        if role in ("user", "assistant") and content:
            messages.append(Message(role, str(content)))
    return messages


async def _load_history(document_id: str) -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = await repo.load_chat_history(session, document_id)
        return [{"role": row.role, "content": row.content, "id": row.id} for row in rows]
