"""Unit tests for signed, expiring download tokens (ARTIFACTS.md §15)."""

from __future__ import annotations

from uuid import uuid4

from app.artifacts.signing import sign_download, verify_download

_SECRET = "test-secret"


def test_roundtrip_preserves_fields() -> None:
    art, org = uuid4(), uuid4()
    token = sign_download(artifact_id=art, org_id=org, version=3, secret=_SECRET, ttl_s=60)
    signed = verify_download(token, secret=_SECRET)
    assert signed is not None
    assert signed.artifact_id == art
    assert signed.org_id == org
    assert signed.version == 3


def test_version_none_roundtrips_as_none() -> None:
    token = sign_download(
        artifact_id=uuid4(), org_id=uuid4(), version=None, secret=_SECRET, ttl_s=60
    )
    signed = verify_download(token, secret=_SECRET)
    assert signed is not None
    assert signed.version is None


def test_wrong_secret_is_rejected() -> None:
    token = sign_download(artifact_id=uuid4(), org_id=uuid4(), version=1, secret=_SECRET, ttl_s=60)
    assert verify_download(token, secret="other-secret") is None


def test_tampered_payload_is_rejected() -> None:
    token = sign_download(artifact_id=uuid4(), org_id=uuid4(), version=1, secret=_SECRET, ttl_s=60)
    payload, sig = token.split(".", 1)
    # Flip the last payload char while keeping the original signature → mismatch.
    tampered = f"{payload[:-1]}{'A' if payload[-1] != 'A' else 'B'}.{sig}"
    assert verify_download(tampered, secret=_SECRET) is None


def test_expired_token_is_rejected() -> None:
    token = sign_download(artifact_id=uuid4(), org_id=uuid4(), version=1, secret=_SECRET, ttl_s=-1)
    assert verify_download(token, secret=_SECRET) is None


def test_malformed_token_is_rejected() -> None:
    assert verify_download("not-a-token", secret=_SECRET) is None
    assert verify_download("", secret=_SECRET) is None
