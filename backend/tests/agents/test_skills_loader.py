"""Unit tests for the skills loader (ARCH §26.3 layering, §26.4 path safety)."""

from __future__ import annotations

import pytest

from app.skills.loader import SkillSource, SkillSourceError, resolve_skill_sources


def test_filesystem_base_ordered_before_uploaded_for_last_wins() -> None:
    # deepagents applies last-wins on name collisions, so uploaded must come AFTER
    # base for an uploaded skill to shadow a base skill of the same name (§26.3).
    sources = [
        SkillSource(name="research", origin="uploaded", path="/skills/uploaded/research"),
        SkillSource(name="research", origin="filesystem", path="/skills/base/research"),
        SkillSource(name="writing", origin="filesystem", path="/skills/base/writing"),
    ]
    resolved = resolve_skill_sources(sources)
    assert resolved == [
        "/skills/base/research",
        "/skills/base/writing",
        "/skills/uploaded/research",
    ]


def test_no_sources_returns_empty_list() -> None:
    assert resolve_skill_sources([]) == []


@pytest.mark.parametrize(
    "bad_path",
    ["skills/base/x", "/skills/../../etc/passwd", "/skills/base/../uploaded/x"],
)
def test_unsafe_paths_are_rejected(bad_path: str) -> None:
    with pytest.raises(SkillSourceError):
        resolve_skill_sources([SkillSource(name="x", origin="uploaded", path=bad_path)])
