"""The HTTP surface: creating rooms, joining them, and being kept out."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coverse.main import create_app
from coverse.ws.rooms import registry


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    registry._rooms.clear()


def test_health_reports_the_provider(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["provider"]["name"] == "mock"


def test_create_then_join_a_room(client):
    code = client.post("/api/rooms", json={}).json()["code"]

    described = client.get(f"/api/rooms/{code}").json()
    assert described["needs_password"] is False

    joined = client.post(f"/api/rooms/{code}/join", json={"name": "Alice"}).json()
    assert joined["name"] == "Alice"
    assert joined["is_driver"] is True, "the first person in should hold the mic"

    second = client.post(f"/api/rooms/{code}/join", json={"name": "Bob"}).json()
    assert second["is_driver"] is False
    assert second["member_id"] != joined["member_id"]
    assert second["color"] != joined["color"], "people need telling apart"


def test_a_password_protected_room_refuses_the_wrong_secret(client):
    code = client.post("/api/rooms", json={"password": "hunter2"}).json()["code"]

    assert client.get(f"/api/rooms/{code}").json()["needs_password"] is True

    wrong = client.post(f"/api/rooms/{code}/join", json={"name": "X", "password": "no"})
    assert wrong.status_code == 403

    right = client.post(f"/api/rooms/{code}/join", json={"name": "X", "password": "hunter2"})
    assert right.status_code == 200


def test_an_unknown_room_is_a_404(client):
    assert client.get("/api/rooms/ZZZZZZ").status_code == 404
    assert client.post("/api/rooms/ZZZZZZ/join", json={"name": "X"}).status_code == 404


def test_a_room_code_is_case_insensitive_when_joining(client):
    code = client.post("/api/rooms", json={}).json()["code"]
    assert client.get(f"/api/rooms/{code.lower()}").status_code == 200


def test_a_full_room_turns_people_away(client, monkeypatch):
    from coverse import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("MAX_MEMBERS_PER_ROOM", "2")
    config.get_settings.cache_clear()

    code = client.post("/api/rooms", json={}).json()["code"]
    room = registry.get(code)

    for name in ("Alice", "Bob"):
        joined = client.post(f"/api/rooms/{code}/join", json={"name": name}).json()
        room.connect(joined["member_id"])  # roster counts people who are online

    assert client.post(f"/api/rooms/{code}/join", json={"name": "Cy"}).status_code == 409


def test_a_blank_name_is_rejected(client):
    code = client.post("/api/rooms", json={}).json()["code"]
    assert client.post(f"/api/rooms/{code}/join", json={"name": ""}).status_code == 422
