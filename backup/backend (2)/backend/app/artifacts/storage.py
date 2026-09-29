"""Object storage for binary artifacts (ARTIFACTS.md §7).

A thin :class:`ObjectStorage` Protocol with a :class:`LocalDiskStorage` dev impl.
The DB stores a ``storage_ref`` (an opaque, org-namespaced key), **never raw bytes**
(§7) and never a raw filesystem path the client could see (§15). In prod the same
Protocol is satisfied by an S3/MinIO implementation — a drop-in, no consumer change
(R2: the seam is the abstraction, not a hand-rolled storage framework).

Keys are built by :func:`object_key` and always lead with ``org_id`` so storage is
isolated per tenant (§7/§15). ``LocalDiskStorage`` additionally refuses any key that
would resolve outside its root (defence-in-depth path-traversal guard) even though
keys are server-generated, never user-supplied.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol
from uuid import UUID

# Keep only a safe, predictable charset in the human-readable filename segment of a
# key; everything routable to a path component is otherwise stripped (the uniqueness
# comes from the artifact_id/version path, not the filename).
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str) -> str:
    """Return ``filename`` reduced to a safe basename (no path components/separators)."""
    base = Path(filename).name or "artifact"
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "artifact"
    return cleaned


def object_key(*, org_id: UUID, artifact_id: UUID, version: int, filename: str) -> str:
    """Build an org-namespaced storage key for one artifact version (§7 tenancy).

    Shape: ``<org_id>/<artifact_id>/v<version>/<safe_filename>``. Leading with the
    org id keeps tenants' objects in disjoint key spaces; the artifact/version path
    makes each immutable snapshot addressable.
    """
    return f"{org_id}/{artifact_id}/v{version}/{safe_filename(filename)}"


class ObjectStorage(Protocol):
    """Minimal blob store: put/get/delete by opaque key (the §7 storage seam)."""

    def put(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key`` (overwriting any existing object)."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes stored under ``key``; raise ``FileNotFoundError`` if absent."""
        ...

    def delete(self, key: str) -> None:
        """Remove the object at ``key`` (idempotent — absent key is a no-op)."""
        ...


class LocalDiskStorage:
    """Filesystem-backed :class:`ObjectStorage` for dev (the MinIO/local option, §7).

    Objects live under ``root/<key>``; parent directories are created on demand. Every
    resolved path is verified to stay within ``root`` so a malformed key can never
    escape the storage tree (R5: validate at the boundary, fail fast).
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        """Resolve ``key`` under the root, rejecting any traversal outside it."""
        candidate = (self._root / key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"artifact storage key escapes root: {key!r}")
        return candidate

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def build_storage(artifacts_dir: str) -> ObjectStorage:
    """Construct the configured object storage (local disk in dev, §7).

    Single factory so callers depend on the :class:`ObjectStorage` Protocol, not the
    concrete impl — swapping in S3/MinIO later is one branch here, no consumer edits.
    """
    return LocalDiskStorage(artifacts_dir)
