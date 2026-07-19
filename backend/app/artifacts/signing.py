"""Signed, expiring download URLs for artifacts (ARTIFACTS.md §15).

A download link must be **signed and expiring** so it can be handed out (embedded in
the AG-UI ``tool_result`` attachment, Slice 2) yet not become a permanent, shareable
capability. We use stdlib ``hmac``/``hashlib`` (HMAC-SHA256) — no third-party
dependency to add or pin (R1) — over a compact payload binding the artifact id, its
org, an optional version, and an absolute expiry.

The token is **defence-in-depth, not the only gate**: the download route still loads
the artifact under Row-Level Security scoped to the token's ``org_id`` (§15 RLS-scoped
downloads), so even a forged token cannot cross tenants. HMAC makes forgery infeasible;
RLS makes a mistake non-catastrophic — both, never one (TECHNICAL §11.7 philosophy).

Token wire format: ``base64url(payload) + "." + base64url(hmac_sha256(secret, payload))``
where ``payload = "<artifact_id>:<org_id>:<version|''>:<expires_epoch>"``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SignedDownload:
    """The verified contents of a download token."""

    artifact_id: UUID
    org_id: UUID
    version: int | None
    expires_at: int


def _b64e(raw: bytes) -> str:
    """URL-safe base64 without padding (compact, query-string safe)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    """Inverse of :func:`_b64e`, restoring stripped padding."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _signature(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return _b64e(digest)


def sign_download(
    *, artifact_id: UUID, org_id: UUID, version: int | None, secret: str, ttl_s: int
) -> str:
    """Mint a signed, expiring token for downloading ``artifact_id`` (§15).

    ``version`` ``None`` ⇒ the link resolves to the artifact's current version at
    download time; a concrete int pins a specific historical version.
    """
    expires_at = int(time.time()) + ttl_s
    payload = f"{artifact_id}:{org_id}:{'' if version is None else version}:{expires_at}"
    payload_b = payload.encode("utf-8")
    return f"{_b64e(payload_b)}.{_signature(payload_b, secret)}"


def verify_download(token: str, *, secret: str) -> SignedDownload | None:
    """Validate a token; return its :class:`SignedDownload`, or ``None`` if invalid.

    ``None`` covers every rejection — malformed shape, bad signature, expired,
    unparseable fields — so the caller maps any failure to a single 403 without
    leaking which check failed (R5: don't leak detail in security paths).
    """
    try:
        payload_part, sig_part = token.split(".", 1)
    except ValueError:
        return None

    payload_b = _b64d(payload_part)
    expected = _signature(payload_b, secret)
    # Constant-time compare to avoid signature-timing oracles.
    if not hmac.compare_digest(sig_part, expected):
        return None

    try:
        artifact_s, org_s, version_s, expires_s = payload_b.decode("utf-8").split(":")
        signed = SignedDownload(
            artifact_id=UUID(artifact_s),
            org_id=UUID(org_s),
            version=int(version_s) if version_s else None,
            expires_at=int(expires_s),
        )
    except ValueError:
        return None

    if signed.expires_at < int(time.time()):
        return None
    return signed
