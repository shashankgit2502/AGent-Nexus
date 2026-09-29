"""ORM model registry (TECHNICAL §11).

Importing this package imports every model module, which registers each table on
``Base.metadata``. ``alembic/env.py`` imports this package so autogenerate (and the
metadata target generally) sees the full schema. Application code imports concrete
models from here.

Includes the §11.4a chat tables (``conversations``/``messages``/``attachments``,
Step 10).
"""

from __future__ import annotations

from app.db.models.conversations import Attachment, Conversation, Message
from app.db.models.identity import Organization, OrgMembership, User
from app.db.models.knowledge import AuditLog, KnowledgeSource, UsageEvent
from app.db.models.models_layer import InferenceProfile, LLMConnection, ModelCatalog
from app.db.models.sessions import Artifact, ArtifactVersion, Run, RunEvent, Session
from app.db.models.teams import Agent, AgentSkill, Skill, Team

__all__ = [
    "Agent",
    "AgentSkill",
    "Artifact",
    "ArtifactVersion",
    "Attachment",
    "AuditLog",
    "Conversation",
    "InferenceProfile",
    "KnowledgeSource",
    "LLMConnection",
    "Message",
    "ModelCatalog",
    "OrgMembership",
    "Organization",
    "Run",
    "RunEvent",
    "Session",
    "Skill",
    "Team",
    "UsageEvent",
    "User",
]
