"""Artifact persistence service (ARTIFACTS.md §7/§8/§9).

The seam the producing tools (Slice 2) and the Synthesizer (§8) call to turn produced
bytes/text into a stored, versioned, downloadable :class:`Artifact`. Kept out of the
router (R5: logic in a service): a router just lists/streams; this owns the
inline-vs-storage decision (§7), the version snapshot write (§9), the size guard
(§15), and signed-URL minting (§15).

Storage policy (§7):
* **binary** (``data`` given) → always object storage; ``content`` NULL.
* **text** (``content`` given) → inline in ``content`` when small; spill to object
  storage when larger than ``ARTIFACT_INLINE_MAX_BYTES`` (``content`` NULL).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts.signing import sign_download
from app.artifacts.storage import ObjectStorage, object_key
from app.core.config import Settings
from app.db.models import Artifact, ArtifactVersion
from app.db.repositories import OrgScopedRepository

logger = logging.getLogger(__name__)


class ArtifactTooLarge(ValueError):
    """Raised when produced bytes exceed ``ARTIFACT_MAX_BYTES`` (§15 size limit)."""


class ArtifactService:
    """Create, snapshot, and serve artifacts for one org (the §7–§9 data path)."""

    def __init__(
        self,
        db: AsyncSession,
        storage: ObjectStorage,
        settings: Settings,
        org_id: UUID,
    ) -> None:
        self._db = db
        self._storage = storage
        self._settings = settings
        self._org_id = org_id
        self._artifacts = OrgScopedRepository(db, Artifact, org_id)
        self._versions = OrgScopedRepository(db, ArtifactVersion, org_id)

    async def create_artifact(
        self,
        *,
        run_id: UUID,
        kind: str,
        filename: str,
        mime_type: str,
        content: str | None = None,
        data: bytes | None = None,
        content_format: str = "markdown",
        producer_agent_id: UUID | None = None,
        conversation_message_id: UUID | None = None,
    ) -> Artifact:
        """Persist a new artifact + its v1 snapshot, storing bytes per §7 policy.

        Exactly one of ``content`` (text) / ``data`` (binary) is expected. Returns the
        flushed :class:`Artifact` (id + defaults populated). Raises
        :class:`ArtifactTooLarge` if the payload exceeds the per-artifact cap (§15).
        """
        if (content is None) == (data is None):
            raise ValueError("create_artifact requires exactly one of `content` or `data`")

        raw = data if data is not None else (content or "").encode("utf-8")
        if len(raw) > self._settings.ARTIFACT_MAX_BYTES:
            raise ArtifactTooLarge(
                f"artifact {filename!r} is {len(raw)} bytes, over the "
                f"{self._settings.ARTIFACT_MAX_BYTES}-byte limit"
            )

        inline = data is None and len(raw) <= self._settings.ARTIFACT_INLINE_MAX_BYTES

        artifact = Artifact(
            org_id=self._org_id,
            run_id=run_id,
            kind=kind,
            filename=filename,
            mime_type=mime_type,
            content=content if inline else None,
            content_format=content_format,
            size_bytes=len(raw),
            current_version=1,
            status="ready",
            producer_agent_id=producer_agent_id,
            conversation_message_id=conversation_message_id,
        )
        # Flush to obtain the id the storage key is built from before writing bytes.
        artifact = await self._artifacts.add(artifact)

        storage_ref: str | None = None
        if not inline:
            storage_ref = object_key(
                org_id=self._org_id, artifact_id=artifact.id, version=1, filename=filename
            )
            self._storage.put(storage_ref, raw)
            artifact.storage_ref = storage_ref

        version = ArtifactVersion(
            org_id=self._org_id,
            artifact_id=artifact.id,
            version=1,
            content=content if inline else None,
            storage_ref=storage_ref,
            size_bytes=len(raw),
        )
        await self._versions.add(version)
        logger.info(
            "artifact created id=%s kind=%s inline=%s size=%d run=%s",
            artifact.id,
            kind,
            inline,
            len(raw),
            run_id,
        )
        return artifact

    async def add_version(
        self, artifact: Artifact, *, content: str, mime_type: str | None = None
    ) -> Artifact:
        """Append a new text version to ``artifact`` and advance ``current_version`` (§9).

        Iterate (ARTIFACTS §10) is the caller: it produces revised content, and this
        persists it as the next immutable :class:`ArtifactVersion` snapshot while the
        artifact row's pointers (``content``/``storage_ref``/``size_bytes``/
        ``current_version``) advance to it. Older versions stay downloadable (Canvas
        history). Storage policy mirrors :meth:`create_artifact` (inline small text,
        spill large to object storage, §7). Raises :class:`ArtifactTooLarge` over the cap.
        """
        raw = content.encode("utf-8")
        if len(raw) > self._settings.ARTIFACT_MAX_BYTES:
            raise ArtifactTooLarge(
                f"revised artifact is {len(raw)} bytes, over the "
                f"{self._settings.ARTIFACT_MAX_BYTES}-byte limit"
            )
        new_version = artifact.current_version + 1
        inline = len(raw) <= self._settings.ARTIFACT_INLINE_MAX_BYTES

        storage_ref: str | None = None
        if not inline:
            storage_ref = object_key(
                org_id=self._org_id,
                artifact_id=artifact.id,
                version=new_version,
                filename=artifact.filename or f"artifact.{artifact.kind}",
            )
            self._storage.put(storage_ref, raw)

        await self._versions.add(
            ArtifactVersion(
                org_id=self._org_id,
                artifact_id=artifact.id,
                version=new_version,
                content=content if inline else None,
                storage_ref=storage_ref,
                size_bytes=len(raw),
            )
        )
        # Advance the artifact row's pointers to the new current version.
        artifact.current_version = new_version
        artifact.content = content if inline else None
        artifact.storage_ref = storage_ref
        artifact.size_bytes = len(raw)
        artifact.status = "ready"
        if mime_type is not None:
            artifact.mime_type = mime_type
        await self._db.flush()
        logger.info("artifact %s iterated to v%d (%d bytes)", artifact.id, new_version, len(raw))
        return artifact

    async def commit(self) -> None:
        """Commit the session — make produced artifacts durable + immediately downloadable.

        The post-consensus producer (ARTIFACTS §2A) runs *inside* the graph, while the
        run's outer transaction commits only at finalization. Each artifact is an
        independent, immutable deliverable, so committing it as it is produced makes the
        signed ``download_url`` carried on its streamed ``tool_result`` valid right away
        (no 404 window), rather than waiting for the run to finalize. The run row's own
        update commits separately at finalization.
        """
        await self._db.commit()

    async def get(self, artifact_id: UUID) -> Artifact | None:
        """Return the artifact by id within this org (RLS + org-filter), or ``None``."""
        return await self._artifacts.get(artifact_id)

    async def list_for_run(self, run_id: UUID) -> Sequence[Artifact]:
        """List a run's artifacts, oldest first (the §14 'run lists them all')."""
        return await self._artifacts.list(order_by="created_at", run_id=run_id)

    async def versions(self, artifact_id: UUID) -> Sequence[ArtifactVersion]:
        """Return an artifact's version snapshots, ascending by version."""
        stmt = (
            select(ArtifactVersion)
            .where(
                ArtifactVersion.org_id == self._org_id,
                ArtifactVersion.artifact_id == artifact_id,
            )
            .order_by(ArtifactVersion.version.asc())
        )
        return (await self._db.scalars(stmt)).all()

    async def get_version(self, artifact_id: UUID, version: int) -> ArtifactVersion | None:
        """Return one specific version snapshot of an artifact, or ``None``."""
        stmt = select(ArtifactVersion).where(
            ArtifactVersion.org_id == self._org_id,
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == version,
        )
        snapshot: ArtifactVersion | None = await self._db.scalar(stmt)
        return snapshot

    def load_bytes(self, *, content: str | None, storage_ref: str | None) -> bytes:
        """Return the downloadable bytes for an artifact/version (inline or stored).

        Pure read off the chosen snapshot: object-storage bytes when ``storage_ref``
        is set, otherwise the inline text encoded as UTF-8.
        """
        if storage_ref is not None:
            return self._storage.get(storage_ref)
        return (content or "").encode("utf-8")

    def signed_url(self, artifact: Artifact, *, version: int | None = None) -> str:
        """Build a signed, expiring download URL for an artifact (§15).

        ``version`` ``None`` ⇒ the link resolves to the current version at fetch time.
        """
        token = sign_download(
            artifact_id=artifact.id,
            org_id=self._org_id,
            version=version,
            secret=self._settings.ARTIFACT_URL_SECRET,
            ttl_s=self._settings.ARTIFACT_URL_TTL_S,
        )
        return f"/artifacts/{artifact.id}/download?token={token}"
