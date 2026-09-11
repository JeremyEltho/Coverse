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


def test_the_model_catalogue_is_listed(client):
    body = client.get("/api/models").json()
    assert body["provider"] == "mock"
    assert body["default"] == "mock-model"
    assert body["error"] is None
    assert {m["id"] for m in body["models"]} >= {"mock-model", "mock-model-large"}


def test_the_catalogue_reports_pricing_per_million_tokens(client):
    models = {m["id"]: m for m in client.get("/api/models").json()["models"]}
    assert models["mock-model"]["free"] is True
    assert models["mock-model-large"]["free"] is False
    assert models["mock-model-large"]["prompt_price"] == 1.5


def test_a_provider_that_cannot_reach_its_catalogue_does_not_break_the_page(client, monkeypatch):
    """The room still works on the configured model, so this is not fatal."""
    from coverse.ai.base import ProviderError
    from coverse.ai.registry import get_provider

    async def boom():
        raise ProviderError("catalogue unreachable")

    monkeypatch.setattr(get_provider(), "list_models", boom)

    body = client.get("/api/models").json()
    assert body["models"] == []
    assert "unreachable" in body["error"]


def test_a_chosen_sprite_is_stored_and_advertised(client):
    code = client.post("/api/rooms", json={}).json()["code"]

    joined = client.post(
        f"/api/rooms/{code}/join", json={"name": "Alice", "sprite": "ghost"}
    ).json()
    assert joined["sprite"] == "ghost"

    from coverse.ws.rooms import registry

    room = registry.get(code)
    room.connect(joined["member_id"])

    # The picker uses this to mark creatures already in the room.
    assert client.get(f"/api/rooms/{code}").json()["sprites"] == ["ghost"]


def test_a_sprite_id_is_sanitised_rather_than_trusted(client):
    code = client.post("/api/rooms", json={}).json()["code"]
    response = client.post(f"/api/rooms/{code}/join", json={"name": "Alice", "sprite": "<script>"})
    assert response.status_code == 422


def test_joining_without_a_sprite_still_works(client):
    """The client falls back to a default, so this must not be required."""
    code = client.post("/api/rooms", json={}).json()["code"]
    assert client.post(f"/api/rooms/{code}/join", json={"name": "Alice"}).status_code == 200
