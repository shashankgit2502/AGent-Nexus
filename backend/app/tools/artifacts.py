"""Text/code artifact-producing tools (ARTIFACTS.md §5, Slice 2).

The first artifact tools: ``write_code_file`` + ``write_markdown`` / ``write_json``
/ ``write_csv``. They are the **post-consensus producer's** tools (§2A) — *not*
added to mesh agents (no competing files mid-debate). Each tool validates its inputs
at the boundary (filename/extension allowlist + JSON well-formedness, §15), persists
through the injected :class:`~app.artifacts.descriptor.ArtifactSink` (which writes the
``artifacts`` row + version and records the standard ``tool_result`` attachment event,
§11.1), and returns an :class:`ArtifactRef` observation so the agent can reference or
later bundle the file (§14).

Generation only (§6): these produce downloadable **bytes**; nothing is executed.
A refusal (bad extension / unparseable JSON / over the size cap) is returned as the
tool observation so the agent can correct and retry — never a crash (R3).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import BaseTool, tool

from app.artifacts.descriptor import ArtifactSink
from app.artifacts.service import ArtifactTooLarge

logger = logging.getLogger(__name__)

# Code/text extensions allowed for download generation (§15 file-type allowlist),
# mapped to a sensible MIME for the download response. Default text/plain.
_CODE_MIME: dict[str, str] = {
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/x-typescript",
    ".tsx": "text/x-typescript",
    ".jsx": "text/javascript",
    ".sql": "application/sql",
    ".html": "text/html",
    ".css": "text/css",
    ".sh": "application/x-sh",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".xml": "application/xml",
    ".toml": "application/toml",
    ".txt": "text/plain",
}
_CODE_EXT = frozenset(_CODE_MIME)


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


async def _persist(
    sink: ArtifactSink,
    *,
    kind: str,
    filename: str,
    mime_type: str,
    content: str,
    content_format: str,
    tool_name: str,
) -> str:
    """Persist one artifact, returning the agent-facing observation or a refusal."""
    try:
        ref = await sink.write_text(
            kind=kind,
            filename=filename,
            mime_type=mime_type,
            content=content,
            content_format=content_format,
            tool=tool_name,
        )
    except ArtifactTooLarge as exc:
        return f"refused: {exc}"
    return ref.as_observation()


def make_artifact_tools(sink: ArtifactSink) -> list[BaseTool]:
    """Build the text/code artifact tools bound to one run's :class:`ArtifactSink` (§5)."""

    @tool
    async def write_code_file(filename: str, language: str, content: str) -> str:
        """Produce a downloadable code/text file (.py/.js/.ts/.sql/.html/...).

        Use for source code or scripts the user should be able to download. ``filename``
        must end in a supported extension; ``language`` labels the syntax for preview.
        """
        ext = _ext(filename)
        if ext not in _CODE_EXT:
            return (
                f"refused: '{filename}' has an unsupported extension. "
                f"Allowed: {sorted(_CODE_EXT)}"
            )
        return await _persist(
            sink,
            kind="code",
            filename=filename,
            mime_type=_CODE_MIME[ext],
            content=content,
            content_format="code",
            tool_name="write_code_file",
        )

    @tool
    async def write_markdown(filename: str, content: str) -> str:
        """Produce a downloadable Markdown document (.md). Use for notes, READMEs, reports."""
        if _ext(filename) not in {".md", ".markdown"}:
            return f"refused: '{filename}' must end in .md (Markdown document)."
        return await _persist(
            sink,
            kind="markdown",
            filename=filename,
            mime_type="text/markdown",
            content=content,
            content_format="markdown",
            tool_name="write_markdown",
        )

    @tool
    async def write_json(filename: str, content: str) -> str:
        """Produce a downloadable JSON file (.json). ``content`` must be valid JSON text."""
        if _ext(filename) != ".json":
            return f"refused: '{filename}' must end in .json."
        try:
            json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            return f"refused: content is not valid JSON ({exc})."
        return await _persist(
            sink,
            kind="json",
            filename=filename,
            mime_type="application/json",
            content=content,
            content_format="json",
            tool_name="write_json",
        )

    @tool
    async def write_csv(filename: str, content: str) -> str:
        """Produce a downloadable CSV file (.csv). ``content`` is the raw CSV text."""
        if _ext(filename) != ".csv":
            return f"refused: '{filename}' must end in .csv."
        return await _persist(
            sink,
            kind="csv",
            filename=filename,
            mime_type="text/csv",
            content=content,
            content_format="csv",
            tool_name="write_csv",
        )

    return [write_code_file, write_markdown, write_json, write_csv]
