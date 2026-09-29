"""Tests for the SSRF guard and validation probe (ARCH §9.4 / §27.3)."""

from __future__ import annotations

import pytest

from app.models_layer.validation import (
    ProbeResult,
    SSRFBlocked,
    probe_model,
    validate_base_url,
)

# ── SSRF guard ────────────────────────────────────────────────────────────────


def test_public_https_url_passes() -> None:
    validate_base_url("https://api.openai.com/v1")  # must not raise


def test_non_http_scheme_blocked() -> None:
    with pytest.raises(SSRFBlocked):
        validate_base_url("file:///etc/passwd")


def test_loopback_blocked_by_default() -> None:
    with pytest.raises(SSRFBlocked):
        validate_base_url("http://localhost:11434")


def test_private_ip_blocked_by_default() -> None:
    # 169.254.169.254 = cloud metadata endpoint, the classic SSRF target.
    with pytest.raises(SSRFBlocked):
        validate_base_url("http://169.254.169.254/latest/meta-data/")


def test_loopback_allowed_when_private_permitted() -> None:
    # Local Ollama: an admin explicitly opts in to a private base_url.
    validate_base_url("http://localhost:11434", allow_private=True)


def test_missing_host_blocked() -> None:
    with pytest.raises(SSRFBlocked):
        validate_base_url("https:///no-host")


# ── Validation probe (model call injected → no network) ───────────────────────


class _OkModel:
    def invoke(self, _prompt: object) -> str:
        return "pong"


class _FailingModel:
    def invoke(self, _prompt: object) -> str:
        raise RuntimeError("401 invalid api key")


def test_probe_ok() -> None:
    result = probe_model(_OkModel())  # type: ignore[arg-type]
    assert result == ProbeResult(ok=True, detail="reachable")


def test_probe_captures_provider_error_without_raising() -> None:
    result = probe_model(_FailingModel())  # type: ignore[arg-type]
    assert result.ok is False
    assert "401 invalid api key" in result.detail
