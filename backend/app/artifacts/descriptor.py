"""Artifact descriptor + the run-scoped sink the producer's tools write through.

This is the bridge between an artifact **tool** (§5) and the AG-UI stream (§11.1):
when the post-consensus producer calls a tool, the tool persists via
:class:`~app.artifacts.service.ArtifactService` and the :class:`ArtifactSink`
records a standard **``tool_result``** event carrying the artifact **descriptor** as
a typed ``attachment`` — *not* a bespoke ``artifact`` event (CLAUDE §3 locked: ride
the standard event types). The descriptor shape is registered in ARCHITECTURE §24.

The sink accumulates the events (returned to the synthesizer node to stream in
order, after the ``synthesis`` event and before ``run_finished``) and the
:class:`ArtifactRef`s (returned to the producer agent so it can reference / later
bundle them, §14).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.artifacts.service import ArtifactService
from app.db.models import Artifact
from app.graph.state import make_event

logger = logging.getLogger(__name__)

# Cap the inline preview carried on the event (§11.1 ``preview``): enough for the
# panel's preview pane without bloating the event/round payload.
_PREVIEW_MAX_CHARS = 4000


def _preview(content: str) -> str:
    """A bounded text preview for the descriptor (§11.1); truncated, never the file."""
    return content if len(content) <= _PREVIEW_MAX_CHARS else content[:_PREVIEW_MAX_CHARS]


def artifact_attachment(
    artifact: Artifact, *, download_url: str, preview: str | None
) -> dict[str, Any]:
    """Build the typed artifact descriptor attached to a ``tool_result`` event (§11.1).

    The frontend ArtifactPanel renders from exactly these fields (kind icon, filename,
    size, version, live ``status``, the ``preview`` for text kinds, and the signed
    ``download_url``). Registered in ARCHITECTURE §24 — keep the two in lockstep.
    """
    return {
        "artifact_id": str(artifact.id),
        "kind": artifact.kind,
        "filename": artifact.filename,
        "mime_type": artifact.mime_type,
        "version": artifact.current_version,
        "status": artifact.status,
        "preview": preview,
        "download_url": download_url,
        "size_bytes": artifact.size_bytes,
    }


@dataclass(frozen=True)
class ArtifactRef:
    """The handle a tool returns to the producer agent (id + filename + link, §5)."""

    artifact_id: UUID
    kind: str
    filename: str
    download_url: str

    def as_observation(self) -> str:
        """The tool-observation string the agent sees (so it can reference/bundle)."""
        return (
            f"Created artifact '{self.filename}' (kind={self.kind}). "
            f"artifact_id={self.artifact_id} download_url={self.download_url}"
        )


@dataclass
class ArtifactSink:
    """Persists produced artifacts and records their ``tool_result`` events (§11.1).

    One sink per producer run. The artifact tools call :meth:`write_text`; the
    synthesizer node collects :attr:`events` (to stream) after the run.
    """

    service: ArtifactService
    run_id: UUID
    producer_agent_id: UUID | None = None
    round: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    refs: list[ArtifactRef] = field(default_factory=list)

    async def write_text(
        self,
        *,
        kind: str,
        filename: str,
        mime_type: str,
        content: str,
        content_format: str,
        tool: str,
    ) -> ArtifactRef:
        """Persist a text/code artifact, record its ``tool_result`` event, return a ref."""
        artifact = await self.service.create_artifact(
            run_id=self.run_id,
            kind=kind,
            filename=filename,
            mime_type=mime_type,
            content=content,
            content_format=content_format,
            producer_agent_id=self.producer_agent_id,
        )
        # Commit immediately so the signed download_url on the streamed tool_result is
        # valid the moment the event reaches the client (artifacts are independent,
        # immutable deliverables — see ArtifactService.commit).
        await self.service.commit()
        download_url = self.service.signed_url(artifact)
        descriptor = artifact_attachment(
            artifact, download_url=download_url, preview=_preview(content)
        )
        producer_id = str(self.producer_agent_id) if self.producer_agent_id else None
        # Standard tool_result event (already in the AG-UI catalog) carrying the
        # descriptor as a typed attachment (§11.1) — no custom event type.
        self.events.append(
            make_event(
                "tool_result",
                agent_id=producer_id or "synthesizer",
                round=self.round,
                tool=tool,
                producer_agent_id=producer_id,
                result=f"created {filename}",
                attachment=descriptor,
            )
        )
        ref = ArtifactRef(
            artifact_id=artifact.id, kind=kind, filename=filename, download_url=download_url
        )
        self.refs.append(ref)
        return ref

    async def load_members(
        self, artifact_ids: list[str] | None
    ) -> list[tuple[str, bytes]]:
        """Resolve artifact ids to ``(filename, bytes)`` for bundling (§14 create_archive).

        Restricted to artifacts of **this run** (and this org, via the service's RLS-scoped
        repo) — a defence-in-depth bound so the producer can only zip what it produced
        here, never reach across runs (§15). Nested archives are skipped. ``None``/empty
        ids ⇒ bundle everything produced so far this run (the "download all files" case).
        """
        ids = artifact_ids or [str(ref.artifact_id) for ref in self.refs]
        members: list[tuple[str, bytes]] = []
        for raw_id in ids:
            try:
                artifact_id = UUID(str(raw_id))
            except ValueError:
                continue
            artifact = await self.service.get(artifact_id)
            if artifact is None or artifact.run_id != self.run_id or artifact.kind == "archive":
                continue
            try:
                data = self.service.load_bytes(
                    content=artifact.content, storage_ref=artifact.storage_ref
                )
            except FileNotFoundError:
                logger.warning("create_archive: bytes missing for %s — skipping", artifact_id)
                continue
            members.append((artifact.filename or f"artifact-{artifact.id}", data))
        return members

    async def write_binary(
        self, *, kind: str, filename: str, mime_type: str, data: bytes, tool: str
    ) -> ArtifactRef:
        """Persist a **binary** artifact (office/media bytes), record its event, return a ref.

        Mirrors :meth:`write_text` for the Slice-4 office/media tools: the bytes always
        go to object storage (§7), so the descriptor's ``preview`` is ``None`` (binary —
        the panel offers download, §12).
        """
        artifact = await self.service.create_artifact(
            run_id=self.run_id,
            kind=kind,
            filename=filename,
            mime_type=mime_type,
            data=data,
            producer_agent_id=self.producer_agent_id,
        )
        await self.service.commit()
        download_url = self.service.signed_url(artifact)
        descriptor = artifact_attachment(artifact, download_url=download_url, preview=None)
        producer_id = str(self.producer_agent_id) if self.producer_agent_id else None
        self.events.append(
            make_event(
                "tool_result",
                agent_id=producer_id or "synthesizer",
                round=self.round,
                tool=tool,
                producer_agent_id=producer_id,
                result=f"created {filename}",
                attachment=descriptor,
            )
        )
        ref = ArtifactRef(
            artifact_id=artifact.id, kind=kind, filename=filename, download_url=download_url
        )
        self.refs.append(ref)
        return ref
