"""Knowledge source DTOs (ARCH §14/§10.5, TECHNICAL §11.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMModel


class DbConnectorConfig(BaseModel):
    """Read-only DB connector config for ``kind='db'`` sources (Slice D, ARCH §10.5.1).

    ``query`` must be a single read-only SELECT; it is run in a read-only transaction
    with a row cap + statement timeout (enforced in the loader, defence-in-depth).
    """

    dsn: str
    query: str


class KnowledgeSourceCreate(BaseModel):
    """Payload to register a RAG source under a team (ARCH §10.5).

    ``agent_id`` NULL = team-shared; set = agent-private (ARCH §10.5.1). Ingestion
    runs on the worker; the row starts ``pending``. ``connector_config`` carries
    kind-specific config — currently the ``db`` connector's ``{dsn, query}``.
    """

    kind: Literal["file", "url", "db", "team_doc"]
    uri: str | None = None
    display_name: str | None = None
    agent_id: UUID | None = None
    connector_config: DbConnectorConfig | None = None


class KnowledgeSourceRead(ORMModel):
    id: UUID
    org_id: UUID
    team_id: UUID
    agent_id: UUID | None
    kind: str
    uri: str | None
    display_name: str | None
    status: str
    # On a failed ingestion, the precise reason (ITEM 2: never a silent failure) so
    # the UI can show *why* and the user can fix the config and re-ingest.
    error: str | None
    chunk_count: int
    created_at: datetime
