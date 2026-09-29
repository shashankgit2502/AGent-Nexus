"""Chat & conversational layer router (ARCH §14 / §8.5).

Thin (R5): conversation/attachment CRUD via the repository; the actual turn
orchestration (team run-per-turn vs no-team single agent) lives in
:mod:`app.chat.service`. The AG-UI stream for a team turn is the WebSocket endpoint
``WS /conversations/{id}/stream`` (mounted from :mod:`app.streaming.websocket`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.chat.service import send_message
from app.core.config import get_settings
from app.core.deps import DbSession, Org
from app.db.models import Attachment, Conversation, KnowledgeSource, Message, Team
from app.db.repositories import OrgScopedRepository
from app.knowledge.worker import spawn_ingestion
from app.schemas.conversations import (
    AttachmentRead,
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
    SendMessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate, db: DbSession, org: Org) -> Conversation:
    """Open a chat: team (multi-agent) or no-team (single LLM) (ARCH §8.5.1)."""
    if payload.team_id is not None:
        if await OrgScopedRepository(db, Team, org.org_id).get(payload.team_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")
    conversation = Conversation(
        org_id=org.org_id,
        team_id=payload.team_id,
        model_ref=payload.model_ref,
        thread_id=payload.thread_id or f"conv-{uuid4()}",
        title=payload.title,
        is_playground=payload.is_playground,
        created_by=org.user_id,
    )
    return await OrgScopedRepository(db, Conversation, org.org_id).add(conversation)


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(db: DbSession, org: Org) -> list[Conversation]:
    """List conversations, **excluding** ephemeral playgrounds (ARCH §8.5.1)."""
    return list(await OrgScopedRepository(db, Conversation, org.org_id).list(is_playground=False))


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
async def get_conversation(conversation_id: UUID, db: DbSession, org: Org) -> Conversation:
    """Fetch one conversation (includes playgrounds, by id)."""
    conversation = await OrgScopedRepository(db, Conversation, org.org_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete a conversation; its messages/attachments cascade via FK (ARCH §8.5)."""
    if not await OrgScopedRepository(db, Conversation, org.org_id).soft_delete(conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(conversation_id: UUID, db: DbSession, org: Org) -> list[Message]:
    """Return a conversation's transcript in chronological order (ARCH §8.5.2).

    Rehydrates a thread on (re)open — the persisted user + assistant turns. Thin
    (R5): the ``(conversation_id, created_at)`` index backs the ordered read.
    """
    conversation = await OrgScopedRepository(db, Conversation, org.org_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return list(
        await OrgScopedRepository(db, Message, org.org_id).list(
            order_by="created_at", conversation_id=conversation_id
        )
    )


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def post_message(
    conversation_id: UUID, payload: MessageCreate, request: Request, db: DbSession, org: Org
) -> SendMessageResponse:
    """Send a user turn; stream/return the assistant reply (ARCH §8.5.2)."""
    conversation = await OrgScopedRepository(db, Conversation, org.org_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return await send_message(
        app=request.app, db=db, org=org, conversation=conversation, payload=payload
    )


def _attachment_read(attachment: Attachment, source: KnowledgeSource | None) -> AttachmentRead:
    """Project an ``Attachment`` (+ its ingestion source) into the read DTO with status.

    Built explicitly because ingestion ``status``/``error`` live on the linked
    ``knowledge_source``, not the attachment row (§8.5.3).
    """
    return AttachmentRead(
        id=attachment.id,
        conversation_id=attachment.conversation_id,
        kind=attachment.kind,
        uri=attachment.uri,
        scope=attachment.scope,  # validated against the Literal by pydantic
        source_id=attachment.source_id,
        status=source.status if source is not None else None,
        error=source.error if source is not None else None,
        promoted_source_id=attachment.promoted_source_id,
        created_at=attachment.created_at,
    )


@router.get("/conversations/{conversation_id}/attachments", response_model=list[AttachmentRead])
async def list_attachments(
    conversation_id: UUID, db: DbSession, org: Org
) -> list[AttachmentRead]:
    """A conversation's uploads with live ingestion status (ARCH §8.5.3 / Bug 2).

    Clients poll this until each attachment reaches a terminal status (``ready`` or
    ``failed``) — so an ingestion failure surfaces in the UI instead of silently.
    """
    conversation = await OrgScopedRepository(db, Conversation, org.org_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")
    attachments = list(
        await OrgScopedRepository(db, Attachment, org.org_id).list(conversation_id=conversation_id)
    )
    source_ids = [a.source_id for a in attachments if a.source_id is not None]
    sources: dict[UUID, KnowledgeSource] = {}
    if source_ids:
        rows = await db.scalars(
            select(KnowledgeSource).where(
                KnowledgeSource.id.in_(source_ids), KnowledgeSource.org_id == org.org_id
            )
        )
        sources = {s.id: s for s in rows}
    return [
        _attachment_read(a, sources.get(a.source_id) if a.source_id else None)
        for a in attachments
    ]


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    conversation_id: UUID, file: UploadFile, db: DbSession, org: Org, request: Request
) -> AttachmentRead:
    """Upload a file as **transient** conversation context and start ingestion (ARCH §8.5.3).

    The bytes are written to the local object-storage root, then ingested through the
    knowledge pipeline as a **conversation-scoped** ``KnowledgeSource`` (``team_id`` may
    be NULL for a no-team chat). Its chunks land in a conversation-private vector
    namespace that only this conversation's per-turn ``search_uploaded_files`` tool can
    read — never the team KB unless explicitly promoted (§8.5.3). The ``Attachment`` row
    is the chat-facing record; ``source_id`` links it to its ingestion source so the UI
    can poll status.
    """
    conversation = await OrgScopedRepository(db, Conversation, org.org_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")

    settings = get_settings()
    data = await file.read()
    if len(data) > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds the {settings.KNOWLEDGE_MAX_UPLOAD_BYTES}-byte upload limit",
        )
    safe_name = Path(file.filename or "upload").name  # strip any path components
    uri = _persist_bytes(conversation_id, safe_name, data)

    # Conversation-scoped ingestion source (reuses the knowledge worker, §10.5.1).
    source = await OrgScopedRepository(db, KnowledgeSource, org.org_id).add(
        KnowledgeSource(
            org_id=org.org_id,
            team_id=conversation.team_id,  # NULL for a no-team chat (org-default embedding)
            conversation_id=conversation_id,
            kind="file",
            uri=uri,
            display_name=safe_name,
            created_by=org.user_id,
        )
    )
    attachment = await OrgScopedRepository(db, Attachment, org.org_id).add(
        Attachment(
            org_id=org.org_id,
            conversation_id=conversation_id,
            kind=file.content_type or "application/octet-stream",
            uri=uri,
            scope="transient",
            source_id=source.id,
        )
    )
    await db.commit()  # commit before spawning so the worker's own session sees the row
    spawn_ingestion(request.app, source_id=source.id, org_id=org.org_id)
    return _attachment_read(attachment, source)  # source just created → status 'pending'


@router.post(
    "/conversations/{conversation_id}/attachments/{attachment_id}/save-to-knowledge",
    response_model=AttachmentRead,
)
async def save_attachment_to_knowledge(
    conversation_id: UUID, attachment_id: UUID, db: DbSession, org: Org
) -> AttachmentRead:
    """Promote a transient attachment into team knowledge (ARCH §8.5.3)."""
    conversation = await OrgScopedRepository(db, Conversation, org.org_id).get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation not found")
    if conversation.team_id is None:
        # No-team chats have no team KB to promote into (ARCH §8.5.3, team chats only).
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="cannot promote: conversation has no team"
        )
    attachment = await OrgScopedRepository(db, Attachment, org.org_id).get(attachment_id)
    if attachment is None or attachment.conversation_id != conversation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="attachment not found")

    promoted = await OrgScopedRepository(db, KnowledgeSource, org.org_id).add(
        KnowledgeSource(
            org_id=org.org_id,
            team_id=conversation.team_id,
            kind="file",
            uri=attachment.uri,
            display_name=Path(attachment.uri).name,
            created_by=org.user_id,
        )
    )
    attachment.scope = "knowledge"
    attachment.promoted_source_id = promoted.id
    await db.flush()
    # Status still reflects the transient ingestion source (the attachment's own upload).
    transient_source = (
        await OrgScopedRepository(db, KnowledgeSource, org.org_id).get(attachment.source_id)
        if attachment.source_id is not None
        else None
    )
    return _attachment_read(attachment, transient_source)


def _persist_bytes(conversation_id: UUID, safe_name: str, data: bytes) -> str:
    """Write the upload bytes to the local object-storage root; return its path (uri)."""
    base = Path(get_settings().ATTACHMENTS_DIR) / str(conversation_id)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / f"{uuid4().hex}_{safe_name}"
    dest.write_bytes(data)
    return str(dest)
