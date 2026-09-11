"""The control socket: `/ws/control/{code}`.

Carries the things that are commands rather than state: send this prompt, stop
that reply, ask for the mic, hand it over, promote a line from the side chat,
ask a private question.

AI output does not travel here. A reply is streamed into the shared document and
reaches everyone through the sync socket, which is what makes spectating work
without any fan-out code. The one exception is a private fork, whose deltas come
back over this socket because they are for one person only.

Client to server:
    {"type": "send",        "body": "..."}          driver only
    {"type": "send_queued", "id": "q_..."}          driver only
    {"type": "stop"}                                anyone
    {"type": "request_mic"}
    {"type": "grant_mic",   "member": "..."}        driver only
    {"type": "release_mic"}                         driver only
    {"type": "sidechat",    "body": "..."}
    {"type": "promote",     "id": "side_..."}
    {"type": "share_fork",  "question": "...", "answer": "..."}
    {"type": "set_model",   "model": "...", "name": "..."}   driver only
    {"type": "queue",       "body": "..."}
    {"type": "fork",        "body": "...", "history": [...]}
    {"type": "ping"}
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..ai import actions
from ..ai.base import ProviderError
from ..ai.registry import get_provider
from ..config import get_settings
from .rooms import Room, registry
from .sync import WS_NOT_FOUND, WS_UNAUTHORIZED

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/control/{code}")
async def control_socket(websocket: WebSocket, code: str, member: str = Query(default="")) -> None:
    room = registry.get(code)
    if room is None:
        await websocket.accept()
        await websocket.close(code=WS_NOT_FOUND, reason="no such room")
        return

    person = room.get_member(member) if member else None
    if person is None:
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED, reason="join the room first")
        return

    await websocket.accept()
    room.connect(member)

    settings = get_settings()
    await websocket.send_json(
        {
            "type": "ready",
            "member_id": member,
            "provider": settings.ai_provider,
            "model": room.state.model or settings.resolved_model,
            "is_driver": room.is_driver(member),
        }
    )

    forks: dict[str, asyncio.Task[None]] = {}

    try:
        while True:
            payload = await websocket.receive_json()
            await _handle(
                websocket=websocket,
                room=room,
                member=member,
                name=person.name,
                payload=payload,
                forks=forks,
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("control socket error in room %s", code)
    finally:
        for task in forks.values():
            if not task.done():
                task.cancel()
        room.disconnect(member)


async def _handle(
    *,
    websocket: WebSocket,
    room: Room,
    member: str,
    name: str,
    payload: dict[str, Any],
    forks: dict[str, asyncio.Task[None]],
) -> None:
    kind = payload.get("type")

    if kind == "ping":
        await websocket.send_json({"type": "pong"})
        return

    # --- the mic ---------------------------------------------------------------

    if kind == "request_mic":
        room.state.request_mic(member, name)
        return

    if kind == "withdraw_request":
        room.state.withdraw_request(member)
        return

    if kind == "grant_mic":
        target = str(payload.get("member") or "")
        if not room.grant_mic(member, target):
            await websocket.send_json(
                {"type": "error", "error": "only the driver can pass the mic"}
            )
        return

    if kind == "release_mic":
        room.release_mic(member)
        return

    # --- side chat and queue ----------------------------------------------------

    if kind == "sidechat":
        body = str(payload.get("body") or "").strip()
        if body:
            room.state.add_sidechat(author=member, author_name=name, body=body)
        return

    if kind == "queue":
        body = str(payload.get("body") or "").strip()
        if body:
            room.state.add_to_queue(author=member, author_name=name, body=body)
        return

    if kind == "promote":
        # Promoting sends to the model, so it costs a turn and belongs to the
        # driver. A spectator who wants a line considered puts it in the queue.
        if not room.is_driver(member):
            await websocket.send_json(
                {"type": "error", "error": "only the driver can promote to the thread"}
            )
            return
        # Move a backchannel line into the thread, attributed to whoever said it.
        target_id = str(payload.get("id") or "")
        for entry in room.state.sidechat:
            item = dict(entry)
            if item.get("id") == target_id:
                await _send_to_ai(
                    websocket=websocket,
                    room=room,
                    member=member,
                    author_name=str(item.get("author_name") or name),
                    body=str(item.get("body") or ""),
                )
                return
        return

    # --- talking to the model ---------------------------------------------------

    if kind in ("send", "send_queued"):
        if not room.is_driver(member):
            await websocket.send_json({"type": "error", "error": "you do not have the mic"})
            return

        if kind == "send_queued":
            queued = room.state.take_from_queue(str(payload.get("id") or ""))
            if queued is None:
                return
            body = str(queued.get("body") or "")
            author_name = str(queued.get("author_name") or name)
        else:
            body = str(payload.get("body") or "").strip()
            author_name = name
            if body:
                # The draft is shared, so clearing it has to be shared too.
                room.state.clear_composer()

        if body:
            await _send_to_ai(
                websocket=websocket,
                room=room,
                member=member,
                author_name=author_name,
                body=body,
            )
        return

    if kind == "stop":
        # Anyone can pull the brake: a reply that is visibly going wrong is
        # wasting everyone's time, not just the driver's.
        job = _running.get(room.code)
        if job and not job.done():
            job.cancel()
        return

    if kind == "set_model":
        # Scoped to the driver for the same reason sending is: it changes what
        # the room's next answer comes from. Takes effect on the next turn, so
        # a reply in flight is never half answered by two models.
        if not room.is_driver(member):
            await websocket.send_json(
                {"type": "error", "error": "only the driver can change the model"}
            )
            return
        model_id = str(payload.get("model") or "").strip()
        if model_id:
            room.state.set_model(model_id, str(payload.get("name") or ""))
        return

    if kind == "share_fork":
        # Bring a private exchange into the room. This publishes what was already
        # said; it does not ask the model anything, so it costs no turn and needs
        # no mic. Re-sending the answer as a prompt would make the assistant
        # reply to its own words.
        question = str(payload.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        if not answer:
            return
        if question:
            room.state.add_message(
                role="user",
                author=member,
                author_name=name,
                body=question,
                shared=True,
            )
        room.state.add_message(
            role="assistant",
            author="assistant",
            author_name="Assistant",
            body=answer,
            shared=True,
            done=True,
        )
        return

    if kind == "fork":
        body = str(payload.get("body") or "").strip()
        if not body:
            return
        job_id = str(payload.get("job") or "fork")
        task = asyncio.create_task(
            _run_fork(
                websocket=websocket,
                room=room,
                name=name,
                body=body,
                history=payload.get("history") or [],
                job_id=job_id,
            )
        )
        forks[job_id] = task

        def _forget(_task: asyncio.Task[None], finished: str = job_id) -> None:
            forks.pop(finished, None)

        task.add_done_callback(_forget)
        return

    await websocket.send_json({"type": "error", "error": f"unknown message: {kind}"})


# One AI reply per room at a time. The mic already enforces one sender, and this
# makes the stop button unambiguous about what it stops.
_running: dict[str, asyncio.Task[None]] = {}


async def _send_to_ai(
    *,
    websocket: WebSocket,
    room: Room,
    member: str,
    author_name: str,
    body: str,
) -> None:
    existing = _running.get(room.code)
    if existing and not existing.done():
        await websocket.send_json({"type": "error", "error": "the assistant is still replying"})
        return

    room.state.add_message(role="user", author=member, author_name=author_name, body=body)

    task = asyncio.create_task(_run_reply(room))
    _running[room.code] = task


async def _run_reply(room: Room) -> None:
    settings = get_settings()
    provider = get_provider()
    room.state.set_running_job("reply")

    try:
        await room.set_ai_presence(True)
        async for _event in actions.reply(
            provider=provider,
            room=room.state,
            flush_ms=settings.stream_flush_ms,
            roster=room.roster(),
            model=room.state.model or settings.resolved_model,
        ):
            pass
    except asyncio.CancelledError:
        # Whatever was already written stays, which is what stopping a speaker
        # mid sentence looks like.
        raise
    except ProviderError as exc:
        logger.warning("provider error in %s: %s", room.code, exc)
        room.state.add_message(role="system", author="system", author_name="System", body=str(exc))
    except Exception as exc:
        logger.exception("reply failed in room %s", room.code)
        room.state.add_message(
            role="system",
            author="system",
            author_name="System",
            body=f"{type(exc).__name__}: {exc}",
        )
    finally:
        room.state.set_running_job(None)
        _running.pop(room.code, None)
        with contextlib.suppress(Exception):
            await room.set_ai_presence(False)


async def _run_fork(
    *,
    websocket: WebSocket,
    room: Room,
    name: str,
    body: str,
    history: list[dict[str, str]],
    job_id: str,
) -> None:
    provider = get_provider()
    try:
        async for event in actions.fork_reply(
            provider=provider,
            room=room.state,
            question=body,
            asker_name=name,
            history=history,
            model=room.state.model or get_settings().resolved_model,
        ):
            await websocket.send_json({**event, "job": job_id, "scope": "fork"})
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"type": "error", "job": job_id, "scope": "fork", "error": str(exc)}
            )
