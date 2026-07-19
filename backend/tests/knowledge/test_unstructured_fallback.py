"""Unit tests for the subprocess-isolated unstructured fallback (ITEM 2 Slice D).

Tests the **isolation/parsing logic** with a stubbed ``subprocess.run`` — deterministic
and fast, without invoking the real (heavy, sometimes-crashing) ``unstructured``. The
key production property: a crash/timeout/error in the child yields ``[]`` so the
source fails cleanly, never taking down the worker.
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from app.knowledge import unstructured_fallback as uf


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_success_returns_document(monkeypatch: pytest.MonkeyPatch) -> None:
    out = json.dumps({"ok": True, "text": "Extracted long-tail content."})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(0, stdout=out))
    docs = uf.partition_with_unstructured("/tmp/x.rtf", "x.rtf")
    assert len(docs) == 1
    assert docs[0].page_content == "Extracted long-tail content."
    assert docs[0].metadata["loader"] == "unstructured"


def test_segfault_returns_empty_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    # A native crash surfaces as a negative return code (signal). Contained → [].
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(-11, stderr="segfault"))
    assert uf.partition_with_unstructured("/tmp/x.rtf", "x.rtf") == []


def test_error_exit_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    out = json.dumps({"ok": False, "error": "PackageNotFoundError"})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(1, stdout=out))
    assert uf.partition_with_unstructured("/tmp/x.rtf", "x.rtf") == []


def test_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*a: object, **k: object) -> None:
        raise subprocess.TimeoutExpired(cmd="runner", timeout=uf._TIMEOUT_S)

    monkeypatch.setattr(subprocess, "run", _raise)
    assert uf.partition_with_unstructured("/tmp/x.rtf", "x.rtf") == []


def test_empty_text_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    out = json.dumps({"ok": True, "text": "   "})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(0, stdout=out))
    assert uf.partition_with_unstructured("/tmp/x.rtf", "x.rtf") == []
