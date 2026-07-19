"""Chat & conversational layer DTOs (ARCH §8.5, §14; TECHNICAL §11.4a)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel
from app.schemas.sessions import RunRead


class ConversationCreate(BaseModel):
    """Payload for ``POST /conversations`` (ARCH §14).

    ``team_id`` set ⇒ team chat (the team collaborates); omitted ⇒ no-team
    single-LLM chat, which then requires ``model_ref`` to choose the model
    (connection/catalog/profile, ARCH §8.5.5). ``is_playground`` ⇒ ephemeral,
    excluded from history.
    """

    team_id: UUID | None = None
    model_ref: dict[str, Any] | None = None
    title: str | None = None
    is_playground: bool = False
    thread_id: str | None = None  # server-generated when omitted

    @model_validator(mode="after")
    def _check_target(self) -> ConversationCreate:
        """A no-team chat must carry a ``model_ref``; playground must be a team chat."""
        if self.team_id is None and self.model_ref is None:
            raise ValueError("a no-team conversation (team_id omitted) requires a model_ref")
        if self.is_playground and self.team_id is None:
            raise ValueError("playground conversations must target a team")
        return self


class ConversationRead(ORMModel):
    """Conversation as returned to clients."""

    id: UUID
    org_id: UUID
    team_id: UUID | None
    model_ref: dict[str, Any] | None
    thread_id: str
    title: str | None
    is_playground: bool
    created_at: datetime


class MessageCreate(BaseModel):
    """Payload for ``POST /conversations/{id}/messages`` — one user turn (ARCH §8.5.2).

    ``deep_collaborate`` (team chat only) selects the full multi-round consensus run
    vs the lightweight 1-round pass (ARCH §8.5.1). Ignored for no-team chat.

    ``attachment_ids`` are uploads (``POST .../attachments``) this turn refers to; the
    backend links them to the user message. The conversation's ingested uploads are
    retrievable via the per-turn ``search_uploaded_files`` tool (ARCH §8.5.3 / Bug 2).
    """

    content: str = Field(min_length=1)
    deep_collaborate: bool = False
    attachment_ids: list[UUID] = Field(default_factory=list)


class MessageRead(ORMModel):
    """A transcript message as returned to clients."""

    id: UUID
    conversation_id: UUID
    role: str
    content: str | None
    run_id: UUID | None
    deep_collaborate: bool
    created_at: datetime


class SendMessageResponse(BaseModel):
    """Result of a user turn: the assistant reply + (team chat) its run & stream.

    For a **team** turn the assistant content is the synthesized output and ``run``/
    ``stream_url`` let the UI expand the turn into the Session Workspace (ARCH §8.5.4).
    For a **no-team** turn there is no run (``run``/``stream_url`` are null) — the
    message is produced directly (ARCH §8.5.2).
    """

    assistant_message: MessageRead
    run: RunRead | None = None
    stream_url: str | None = None


class AttachmentRead(ORMModel):
    """A chat file upload as returned to clients (ARCH §8.5.3)."""

    id: UUID
    conversation_id: UUID
    kind: str
    uri: str
    scope: Literal["transient", "knowledge"]
    source_id: UUID | None  # the conversation-scoped ingestion source (status lives there)
    # Ingestion lifecycle of the linked source, surfaced so the UI shows progress and
    # never a silent failure (ARCH §8.5.3 / Bug 2). None when there is no linked source.
    status: Literal["pending", "ingesting", "ready", "failed"] | None = None
    error: str | None = None
    promoted_source_id: UUID | None
    created_at: datetime
