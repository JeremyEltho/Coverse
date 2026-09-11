"""Creating and joining rooms.

Joining is the only place identity is established: you pick a name, you get a
member id for the life of the room, and that is the whole account system.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..ws.rooms import registry

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777"]


class RoomCreate(BaseModel):
    password: str = Field(default="", max_length=128)


class RoomJoin(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    password: str = Field(default="", max_length=128)
    # A sprite id from the client's catalogue. Deliberately not validated
    # against a server-side copy of that list: duplicating it here would drift
    # the moment a creature is added. It is sanitised to a slug, and the client
    # falls back to a default for anything it does not recognise.
    sprite: str = Field(default="", max_length=24, pattern=r"^[a-z0-9-]*$")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(body: RoomCreate) -> dict[str, Any]:
    room = await registry.create(body.password)
    return {"code": room.code, "needs_password": room.needs_password}


@router.get("/{code}")
async def describe_room(code: str) -> dict[str, Any]:
    """What a joiner needs before they are in: does it exist, is it locked."""
    room = registry.get(code)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such room")
    return {
        "code": room.code,
        "needs_password": room.needs_password,
        "members": room.roster(),
        # So the picker can mark creatures already in the room. Marked, not
        # blocked: being told your first choice is unavailable is worse than
        # occasionally matching someone.
        "sprites": [m.sprite for m in room.members.values() if m.sprite and m.online],
    }


@router.post("/{code}/join")
async def join_room(code: str, body: RoomJoin) -> dict[str, Any]:
    room = registry.get(code)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such room")
    if not room.check_password(body.password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "wrong room password")
    if len(room.roster()) >= room._settings.max_members_per_room:
        raise HTTPException(status.HTTP_409_CONFLICT, "room is full")

    color = PALETTE[len(room.members) % len(PALETTE)]
    member = room.add_member(body.name, color, body.sprite)
    return {
        "code": room.code,
        "member_id": member.id,
        "name": member.name,
        "color": member.color,
        "sprite": member.sprite,
        "is_driver": room.is_driver(member.id),
    }
