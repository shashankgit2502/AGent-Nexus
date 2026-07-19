"""Skills loader — ordered, layered skill source paths (ARCHITECTURE.md §11/§26).

`deepagents` 0.6.10 consumes skills as a list of **source paths** relative to the
agent's backend root (``create_deep_agent(skills=[...])`` → ``SkillsMiddleware``);
only each skill's name + description is loaded up front (progressive disclosure,
§26.2), and **later sources override earlier ones on a name collision**
(last-wins, §26.3). This module's job is therefore to turn an agent's selected
skills into that correctly-ordered, validated path list.

Locked layering (§26.3): **filesystem base** (lowest precedence) → **UI-uploaded**
(highest). We emit base paths first and uploaded paths last so deepagents'
last-wins semantics make an uploaded skill shadow a base skill of the same name.

R1 note: verified against deepagents 0.6.10 that ``skills`` is ``list[str]`` of
source paths and that ordering controls precedence (``create_deep_agent`` docstring
+ ``SkillsMiddleware(sources=...)``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Lowest→highest precedence. The tuple order is also the emit order, so the
# loader's layering is derived from this single source of truth.
SkillOrigin = Literal["filesystem", "uploaded"]
_PRECEDENCE: tuple[SkillOrigin, ...] = ("filesystem", "uploaded")


class SkillSourceError(ValueError):
    """An uploaded/base skill declares an unsafe or malformed source path (§26.4)."""


class SkillSource(BaseModel):
    """One skill made available to an agent, with where it comes from.

    ``path`` is the skill's directory **within the agent backend root** (e.g.
    ``/skills/base/market-research`` for a filesystem base skill, or
    ``/skills/uploaded/market-research`` for a store-backed uploaded one). It is
    not a host filesystem path — it is resolved by the agent's backend.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    origin: SkillOrigin
    path: str


def _validate_skill_path(path: str) -> str:
    """Reject traversal / non-rooted skill paths before they reach a backend (§26.4).

    Uploaded skills are untrusted input; a ``..`` segment or a non-absolute path
    could escape the skill root. We fail fast with a clear error (R3 — no silent
    band-aid) rather than letting a backend resolve something unexpected.
    """
    if not path.startswith("/"):
        raise SkillSourceError(
            f"skill source path must be backend-absolute (start with '/'): {path!r}"
        )
    segments = [seg for seg in path.split("/") if seg]
    if any(seg == ".." for seg in segments):
        raise SkillSourceError(f"skill source path must not contain '..' traversal: {path!r}")
    return path


def resolve_skill_sources(sources: Iterable[SkillSource]) -> list[str]:
    """Return validated skill source paths ordered base→uploaded (last-wins, §26.3).

    Args:
        sources: the agent's selected skills (any order).

    Returns:
        Path strings ready for ``create_deep_agent(skills=...)``: every
        filesystem-base path first, then every uploaded path, each validated.
        Returns ``[]`` when the agent has no skills (the factory passes
        ``None`` in that case so deepagents skips ``SkillsMiddleware``).

    Raises:
        SkillSourceError: a source declares an unsafe path (§26.4).
    """
    ordered: list[str] = []
    materialised: Sequence[SkillSource] = list(sources)
    for origin in _PRECEDENCE:
        for source in materialised:
            if source.origin == origin:
                ordered.append(_validate_skill_path(source.path))
    return ordered
