"""REST endpoints for managing documents and their suggestions."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import User, current_user
from ..crdt import suggestions as suggestion_store
from ..db import repo
from ..db.session import session_scope
from ..ws.rooms import room_manager

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=500)
    mode: Literal["doc", "canvas"] = "doc"


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    mode: Literal["doc", "canvas"] | None = None
    link_access: Literal["editor", "none"] | None = None


class DocumentOut(BaseModel):
    id: str
    title: str
    mode: str
    owner_id: str
    link_access: str
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, document: Any) -> DocumentOut:
        return cls(
            id=document.id,
            title=document.title,
            mode=document.mode,
            owner_id=document.owner_id,
            link_access=document.link_access,
            created_at=document.created_at.isoformat(),
            updated_at=document.updated_at.isoformat(),
        )


class CollaboratorIn(BaseModel):
    user_id: str
    role: Literal["editor", "viewer"] = "editor"


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: User = Depends(current_user)) -> list[DocumentOut]:
    async with session_scope() as session:
        return [DocumentOut.of(d) for d in await repo.list_documents(session, user.id)]


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(body: DocumentCreate, user: User = Depends(current_user)) -> DocumentOut:
    async with session_scope() as session:
        document = await repo.create_document(
            session, owner_id=user.id, title=body.title, mode=body.mode
        )
        return DocumentOut.of(document)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, user: User = Depends(current_user)) -> DocumentOut:
    async with session_scope() as session:
        document = await _require_access(session, document_id, user.id)
        return DocumentOut.of(document)


@router.patch("/{document_id}", response_model=DocumentOut)
async def patch_document(
    document_id: str, body: DocumentPatch, user: User = Depends(current_user)
) -> DocumentOut:
    async with session_scope() as session:
        await _require_access(session, document_id, user.id)
        document = await repo.update_document(
            session,
            document_id,
            title=body.title,
            mode=body.mode,
            link_access=body.link_access,
        )
        assert document is not None
        return DocumentOut.of(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, user: User = Depends(current_user)) -> None:
    async with session_scope() as session:
        document = await _require_access(session, document_id, user.id)
        if document.owner_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can delete")
        await repo.delete_document(session, document_id)


@router.post("/{document_id}/collaborators", status_code=status.HTTP_204_NO_CONTENT)
async def add_collaborator(
    document_id: str, body: CollaboratorIn, user: User = Depends(current_user)
) -> None:
    async with session_scope() as session:
        document = await _require_access(session, document_id, user.id)
        if document.owner_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can invite")
        await repo.add_collaborator(
            session, document_id=document_id, user_id=body.user_id, role=body.role
        )


@router.get("/{document_id}/content")
async def get_content(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    """The document as markdown. Useful for export and for debugging the CRDT."""
    async with session_scope() as session:
        await _require_access(session, document_id, user.id)
    room = await room_manager.get(document_id)
    return {
        "id": document_id,
        "markdown": room.doc.to_markdown(),
        "xml": room.doc.to_xml(),
        "connected": len(room.clients),
    }


@router.get("/{document_id}/suggestions")
async def list_suggestions(
    document_id: str, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    async with session_scope() as session:
        await _require_access(session, document_id, user.id)
    room = await room_manager.get(document_id)
    return suggestion_store.list_pending(room.doc.suggestions)


@router.delete("/{document_id}/suggestions/{suggestion_id}", status_code=204)
async def dismiss_suggestion(
    document_id: str, suggestion_id: str, user: User = Depends(current_user)
) -> None:
    """Reject a suggestion.

    Accepting one happens on the client, which resolves the stored relative
    position against its own editor state and applies the edit through TipTap.
    """
    async with session_scope() as session:
        await _require_access(session, document_id, user.id)
    room = await room_manager.get(document_id)
    suggestion_store.remove(room.doc.suggestions, suggestion_id)


async def _require_access(session: Any, document_id: str, user_id: str) -> Any:
    document = await repo.get_document(session, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    if not await repo.user_can_access(session, document_id, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to this document")
    return document
