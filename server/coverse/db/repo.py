"""Queries. Kept thin and explicit rather than hidden behind an ORM layer."""

from __future__ import annotations

from typing import Any

from pycrdt import merge_updates
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatMessage, Document, DocumentCollaborator, DocumentUpdate


async def create_document(
    session: AsyncSession, *, owner_id: str, title: str = "Untitled", mode: str = "doc"
) -> Document:
    document = Document(owner_id=owner_id, title=title, mode=mode)
    session.add(document)
    await session.flush()
    return document


async def create_document_with_id(
    session: AsyncSession,
    *,
    document_id: str,
    owner_id: str,
    title: str = "Untitled",
    mode: str = "doc",
) -> Document:
    """Create a document under a caller-supplied id.

    Used when a client connects to a document id that does not exist yet, which
    is how a brand new URL becomes a real document.
    """
    document = Document(id=document_id, owner_id=owner_id, title=title, mode=mode)
    session.add(document)
    await session.flush()
    return document


async def get_document(session: AsyncSession, document_id: str) -> Document | None:
    return await session.get(Document, document_id)


async def list_documents(session: AsyncSession, user_id: str) -> list[Document]:
    """Documents the user owns or collaborates on, newest first."""
    collaborating = select(DocumentCollaborator.document_id).where(
        DocumentCollaborator.user_id == user_id
    )
    result = await session.execute(
        select(Document)
        .where(or_(Document.owner_id == user_id, Document.id.in_(collaborating)))
        .order_by(Document.updated_at.desc())
    )
    return list(result.scalars().all())


async def user_can_access(session: AsyncSession, document_id: str, user_id: str) -> bool:
    """Whether this user may read and edit the document.

    Access comes from being the owner, from an explicit invitation, or from the
    document's link setting -- the "anyone with the link" behaviour people expect
    from a collaborative editor. Owners can turn that off per document.
    """
    document = await get_document(session, document_id)
    if document is None:
        return False
    if document.owner_id == user_id:
        return True

    if await is_explicit_collaborator(session, document_id, user_id):
        return True

    return document.link_access != "none"


async def join_via_link(session: AsyncSession, document_id: str, user_id: str) -> bool:
    """Let a link visitor in, recording them as a collaborator.

    Recording the join is what makes the document appear in their list and their
    name show up for the owner, instead of them being a permanent stranger who
    happens to have access.
    """
    document = await get_document(session, document_id)
    if document is None:
        return False
    if document.owner_id == user_id:
        return True
    if document.link_access == "none":
        return await user_can_access(session, document_id, user_id)

    await add_collaborator(session, document_id=document_id, user_id=user_id)
    return True


async def is_explicit_collaborator(session: AsyncSession, document_id: str, user_id: str) -> bool:
    """Whether there is a real collaborator row, ignoring link access."""
    result = await session.execute(
        select(DocumentCollaborator.id).where(
            DocumentCollaborator.document_id == document_id,
            DocumentCollaborator.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def add_collaborator(
    session: AsyncSession, *, document_id: str, user_id: str, role: str = "editor"
) -> None:
    """Record an explicit collaborator.

    The guard deliberately checks for an existing row rather than calling
    `user_can_access`: with link sharing on, everyone already "has access", so
    reusing that check here would skip the insert and the document would never
    appear in the collaborator's list.
    """
    document = await get_document(session, document_id)
    if document is not None and document.owner_id == user_id:
        return
    if await is_explicit_collaborator(session, document_id, user_id):
        return
    session.add(DocumentCollaborator(document_id=document_id, user_id=user_id, role=role))


async def update_document(
    session: AsyncSession, document_id: str, **changes: Any
) -> Document | None:
    document = await get_document(session, document_id)
    if document is None:
        return None
    for key, value in changes.items():
        if value is not None and hasattr(document, key):
            setattr(document, key, value)
    return document


async def delete_document(session: AsyncSession, document_id: str) -> None:
    await session.execute(delete(Document).where(Document.id == document_id))


# --- Yjs update log --------------------------------------------------------------


async def append_update(session: AsyncSession, document_id: str, update: bytes) -> None:
    session.add(DocumentUpdate(document_id=document_id, update=update))


async def load_updates(session: AsyncSession, document_id: str) -> list[bytes]:
    result = await session.execute(
        select(DocumentUpdate.update)
        .where(DocumentUpdate.document_id == document_id)
        .order_by(DocumentUpdate.id)
    )
    return [row for row in result.scalars().all()]


async def count_updates(session: AsyncSession, document_id: str) -> int:
    result = await session.execute(
        select(func.count(DocumentUpdate.id)).where(DocumentUpdate.document_id == document_id)
    )
    return int(result.scalar_one())


async def compact_updates(session: AsyncSession, document_id: str) -> int:
    """Collapse the update log into one merged row.

    Yjs updates merge associatively, so the log can always be replaced by a single
    equivalent update. Returns the number of rows removed.
    """
    updates = await load_updates(session, document_id)
    if len(updates) <= 1:
        return 0

    merged = merge_updates(*updates)
    await session.execute(delete(DocumentUpdate).where(DocumentUpdate.document_id == document_id))
    session.add(DocumentUpdate(document_id=document_id, update=merged))
    return len(updates) - 1


# --- chat -----------------------------------------------------------------------


async def append_chat_message(
    session: AsyncSession,
    *,
    document_id: str,
    user_id: str,
    role: str,
    content: str,
    provider: str = "",
    model: str = "",
) -> ChatMessage:
    message = ChatMessage(
        document_id=document_id,
        user_id=user_id,
        role=role,
        content=content,
        provider=provider,
        model=model,
    )
    session.add(message)
    await session.flush()
    return message


async def load_chat_history(
    session: AsyncSession, document_id: str, limit: int = 50
) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.document_id == document_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))
