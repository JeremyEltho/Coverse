"""Room membership, the mic, and the graces that keep it usable."""

from __future__ import annotations

import asyncio

import pytest

from coverse.ws.rooms import Room, RoomRegistry, generate_code


def _member(room: Room, name: str):
    member = room.add_member(name, "#000")
    room.connect(member.id)
    return member


def test_the_first_person_in_gets_the_mic():
    room = Room("TEST01")
    alice = _member(room, "Alice")
    bob = _member(room, "Bob")

    assert room.is_driver(alice.id)
    assert not room.is_driver(bob.id)
    assert room.state.driver_name == "Alice"


def test_only_the_driver_can_pass_the_mic():
    room = Room("TEST02")
    alice = _member(room, "Alice")
    bob = _member(room, "Bob")
    cy = _member(room, "Cy")

    assert room.grant_mic(bob.id, cy.id) is False, "a spectator cannot hand out the mic"
    assert room.is_driver(alice.id)

    assert room.grant_mic(alice.id, bob.id) is True
    assert room.is_driver(bob.id)
    assert room.state.driver_name == "Bob"


def test_releasing_the_mic_passes_it_to_the_longest_present_member():
    room = Room("TEST03")
    alice = _member(room, "Alice")
    bob = _member(room, "Bob")

    room.grant_mic(alice.id, bob.id)
    assert room.release_mic(bob.id) is True
    assert room.is_driver(alice.id)


def test_a_password_gates_joining():
    room = Room("TEST04", password="hunter2")
    assert room.needs_password
    assert room.check_password("hunter2")
    assert not room.check_password("wrong")
    assert not room.check_password("")


def test_no_password_lets_anyone_in():
    room = Room("TEST05")
    assert not room.needs_password
    assert room.check_password("")


def test_presence_counts_connections_so_a_second_tab_does_not_look_like_leaving():
    room = Room("TEST06")
    alice = _member(room, "Alice")
    room.connect(alice.id)  # a second socket for the same person

    room.disconnect(alice.id)
    assert alice.online, "one socket closing must not empty the room"

    room.disconnect(alice.id)
    assert not alice.online
    assert room.is_empty


async def test_an_absent_driver_loses_the_mic_after_the_grace_period(monkeypatch):
    """One dropped laptop must not block the room forever."""
    from coverse import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("DRIVER_GRACE_SECONDS", "0.05")
    config.get_settings.cache_clear()

    room = Room("TEST07")
    alice = _member(room, "Alice")
    bob = _member(room, "Bob")
    assert room.is_driver(alice.id)

    room.disconnect(alice.id)
    await asyncio.sleep(0.2)

    assert room.is_driver(bob.id), "the mic should have moved to the remaining member"


async def test_a_driver_who_reconnects_in_time_keeps_the_mic(monkeypatch):
    from coverse import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("DRIVER_GRACE_SECONDS", "0.3")
    config.get_settings.cache_clear()

    room = Room("TEST08")
    alice = _member(room, "Alice")
    _member(room, "Bob")

    room.disconnect(alice.id)
    room.connect(alice.id)  # a refresh, not a departure
    await asyncio.sleep(0.5)

    assert room.is_driver(alice.id)


def test_room_codes_avoid_ambiguous_characters():
    """The code gets read aloud across a table, so 0/O and 1/I are out."""
    codes = "".join(generate_code() for _ in range(200))
    assert not set(codes) & set("O0I1L")


async def test_the_registry_creates_unique_rooms_and_closes_them():
    registry = RoomRegistry()
    first = await registry.create()
    second = await registry.create()

    assert first.code != second.code
    assert registry.get(first.code.lower()) is first, "codes are case insensitive"
    assert registry.exists(first.code)

    await registry.close_all()
    assert registry.get(first.code) is None


@pytest.mark.parametrize("password", ["", "secret"])
async def test_registry_rooms_carry_their_password(password: str):
    registry = RoomRegistry()
    room = await registry.create(password)
    assert room.needs_password is bool(password)
    await registry.close_all()
