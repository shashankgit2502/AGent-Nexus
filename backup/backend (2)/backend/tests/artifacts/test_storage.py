"""Unit tests for the artifact object-storage seam (ARTIFACTS.md §7)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.artifacts.storage import LocalDiskStorage, object_key, safe_filename


def test_safe_filename_strips_paths_and_unsafe_chars() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("my report (final).xlsx") == "my_report_final_.xlsx"
    assert safe_filename("") == "artifact"
    assert safe_filename("///") == "artifact"


def test_object_key_is_org_namespaced() -> None:
    org, art = uuid4(), uuid4()
    key = object_key(org_id=org, artifact_id=art, version=2, filename="model.xlsx")
    # Leads with the org id (tenant isolation, §7) and addresses the version.
    assert key == f"{org}/{art}/v2/model.xlsx"


def test_local_disk_put_get_delete_roundtrip(tmp_path: Path) -> None:
    storage = LocalDiskStorage(str(tmp_path))
    key = f"{uuid4()}/file.bin"
    payload = b"\x00\x01binary\xff"

    storage.put(key, payload)
    assert storage.get(key) == payload

    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.get(key)
    # Deleting an absent key is a no-op (idempotent cleanup).
    storage.delete(key)


def test_local_disk_rejects_traversal_keys(tmp_path: Path) -> None:
    storage = LocalDiskStorage(str(tmp_path))
    with pytest.raises(ValueError):
        storage.put("../escape.txt", b"x")
    with pytest.raises(ValueError):
        storage.get("../../etc/passwd")
