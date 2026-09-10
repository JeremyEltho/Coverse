"""HTTP surface, auth, and access control."""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from coverse.auth import AuthError, verify_token
from coverse.config import Settings
from coverse.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _auth(user: str) -> dict[str, str]:
    return {"authorization": user}


def test_health_reports_provider_and_auth_mode(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["provider"]["name"] == "mock"
    assert body["auth"] == "dev"


def test_document_crud(client):
    created = client.post("/api/documents", json={"title": "Notes"}, headers=_auth("u1"))
    assert created.status_code == 201
    document_id = created.json()["id"]

    assert client.get(f"/api/documents/{document_id}", headers=_auth("u1")).status_code == 200

    patched = client.patch(
        f"/api/documents/{document_id}", json={"title": "Renamed"}, headers=_auth("u1")
    )
    assert patched.json()["title"] == "Renamed"

    assert client.delete(f"/api/documents/{document_id}", headers=_auth("u1")).status_code == 204
    assert client.get(f"/api/documents/{document_id}", headers=_auth("u1")).status_code == 404


def test_anyone_with_the_link_can_open_a_document_by_default(client):
    """Link sharing is the default, the way a collaborative editor is expected to work."""
    document_id = client.post(
        "/api/documents", json={"title": "Shared"}, headers=_auth("u1")
    ).json()["id"]

    assert client.get(f"/api/documents/{document_id}", headers=_auth("u2")).status_code == 200


def test_link_access_can_be_restricted_to_the_owner_and_invitees(client):
    document_id = client.post(
        "/api/documents", json={"title": "Private"}, headers=_auth("u1")
    ).json()["id"]

    client.patch(f"/api/documents/{document_id}", json={"link_access": "none"}, headers=_auth("u1"))

    assert client.get(f"/api/documents/{document_id}", headers=_auth("u2")).status_code == 403
    assert client.get("/api/documents", headers=_auth("u2")).json() == []

    client.post(
        f"/api/documents/{document_id}/collaborators", json={"user_id": "u2"}, headers=_auth("u1")
    )
    assert client.get(f"/api/documents/{document_id}", headers=_auth("u2")).status_code == 200


def test_a_stranger_can_never_delete_someone_elses_document(client):
    """Read access via a link must not imply ownership."""
    document_id = client.post(
        "/api/documents", json={"title": "Shared"}, headers=_auth("u1")
    ).json()["id"]

    assert client.delete(f"/api/documents/{document_id}", headers=_auth("u2")).status_code == 403
    assert client.get(f"/api/documents/{document_id}", headers=_auth("u1")).status_code == 200


def test_an_invited_collaborator_sees_the_document_in_their_list(client):
    document_id = client.post(
        "/api/documents", json={"title": "Shared"}, headers=_auth("u1")
    ).json()["id"]

    invited = client.post(
        f"/api/documents/{document_id}/collaborators",
        json={"user_id": "u2"},
        headers=_auth("u1"),
    )
    assert invited.status_code == 204
    assert len(client.get("/api/documents", headers=_auth("u2")).json()) == 1


def test_only_the_owner_can_invite(client):
    document_id = client.post("/api/documents", json={}, headers=_auth("u1")).json()["id"]
    client.post(
        f"/api/documents/{document_id}/collaborators", json={"user_id": "u2"}, headers=_auth("u1")
    )
    response = client.post(
        f"/api/documents/{document_id}/collaborators", json={"user_id": "u3"}, headers=_auth("u2")
    )
    assert response.status_code == 403


def test_hs256_tokens_are_verified():
    secret = "a" * 40
    settings = Settings(supabase_jwt_secret=secret)
    token = jwt.encode(
        {"sub": "user-42", "email": "a@b.com", "user_metadata": {"full_name": "Jeremy"}},
        secret,
        algorithm="HS256",
    )
    user = verify_token(token, settings)
    assert user.id == "user-42"
    assert user.display_name == "Jeremy"


def test_a_token_signed_with_the_wrong_secret_is_rejected():
    settings = Settings(supabase_jwt_secret="a" * 40)
    forged = jwt.encode({"sub": "attacker"}, "b" * 40, algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(forged, settings)


def test_dev_auth_is_refused_when_auth_is_required():
    settings = Settings(auth_required=True)
    with pytest.raises(AuthError):
        verify_token("any-token", settings)
