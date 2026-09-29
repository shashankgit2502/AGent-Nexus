"""Office + media artifact tools (ARTIFACTS.md §5/§13, Slice 4).

The producer's binary deliverable tools: ``create_docx`` / ``create_xlsx`` /
``create_pptx`` / ``create_pdf`` / ``create_chart`` / ``create_image``. Each validates
its spec, generates bytes via :mod:`app.artifacts.generators` **off the event loop**
(``asyncio.to_thread`` — heavy CPU generation never blocks the loop, the same offload
the knowledge worker uses, §16), and persists through the run's
:class:`~app.artifacts.descriptor.ArtifactSink` (binary → object storage, §7) as a
standard ``tool_result`` attachment (§11.1).

Capability gate (§13): ``doc_chart`` ("Create documents/charts/code") grants the text
tools + the office/chart tools; ``image_gen`` ("Create images") grants ``create_image``
(+ ``create_chart``). Tools are assembled per the producer agent's capabilities so a
reviewer agent can't emit files while a builder can.

Generation only (§6): these produce downloadable bytes; nothing is executed. A bad
spec / oversize file is returned as a refusal observation, never a crash (R3).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.artifacts.descriptor import ArtifactSink
from app.artifacts.generators import (
    BINARY_FORMATS,
    build_archive,
    build_chart,
    build_docx,
    build_image,
    build_pdf,
    build_pptx,
    build_xlsx,
)
from app.artifacts.service import ArtifactTooLarge
from app.tools.artifacts import make_artifact_tools

logger = logging.getLogger(__name__)


def _with_extension(filename: str, extension: str) -> str:
    """Ensure ``filename`` ends with the format's extension (e.g. ``.docx``)."""
    if filename.lower().endswith(extension):
        return Path(filename).name
    return f"{Path(filename).stem or 'artifact'}{extension}"


async def _persist_binary(
    sink: ArtifactSink,
    *,
    format_key: str,
    filename: str,
    generate: Callable[[], bytes],
    tool_name: str,
) -> str:
    """Generate bytes off-loop and persist them, returning the observation or a refusal."""
    artifact_kind, mime_type, extension = BINARY_FORMATS[format_key]
    safe_name = _with_extension(filename, extension)
    try:
        data = await asyncio.to_thread(generate)
    except ValueError as exc:  # spec validation failure → the agent can correct it.
        return f"refused: {exc}"
    except Exception as exc:  # noqa: BLE001 — generation error surfaced to the agent, logged.
        logger.exception("artifact generation failed (%s)", tool_name)
        return f"failed to generate {safe_name}: {type(exc).__name__}: {exc}"
    try:
        ref = await sink.write_binary(
            kind=artifact_kind, filename=safe_name, mime_type=mime_type, data=data, tool=tool_name
        )
    except ArtifactTooLarge as exc:
        return f"refused: {exc}"
    return ref.as_observation()


def make_office_tools(sink: ArtifactSink) -> list[BaseTool]:
    """The document/chart tools granted by the ``doc_chart`` capability (§13)."""

    @tool
    async def create_docx(filename: str, title: str, sections: list[dict[str, Any]]) -> str:
        """Produce a downloadable Word document (.docx).

        sections: a list of objects, each {"heading": str (optional), "body": str
        (optional; blank lines split paragraphs)}. Example: [{"heading": "Summary",
        "body": "First paragraph.\\n\\nSecond paragraph."}].
        """
        return await _persist_binary(
            sink,
            format_key="docx",
            filename=filename,
            generate=lambda: build_docx(title=title, sections=sections),
            tool_name="create_docx",
        )

    @tool
    async def create_xlsx(filename: str, sheets: list[dict[str, Any]]) -> str:
        """Produce a downloadable Excel workbook (.xlsx).

        sheets: a non-empty list of objects {"name": str, "rows": list of rows}, where
        each row is a list of cells (numbers/strings); a cell string starting with "="
        is an Excel formula. Example: [{"name": "Q1", "rows": [["Item", "Cost"],
        ["Widget", 10], ["Total", "=SUM(B2:B2)"]]}].
        """
        return await _persist_binary(
            sink,
            format_key="xlsx",
            filename=filename,
            generate=lambda: build_xlsx(sheets=sheets),
            tool_name="create_xlsx",
        )

    @tool
    async def create_pptx(filename: str, slides: list[dict[str, Any]]) -> str:
        """Produce a downloadable PowerPoint deck (.pptx).

        slides: a non-empty list of objects {"title": str, "bullets": list of strings}.
        Example: [{"title": "Plan", "bullets": ["Step one", "Step two"]}].
        """
        return await _persist_binary(
            sink,
            format_key="pptx",
            filename=filename,
            generate=lambda: build_pptx(slides=slides),
            tool_name="create_pptx",
        )

    @tool
    async def create_pdf(filename: str, content_md: str) -> str:
        """Produce a downloadable PDF (.pdf) from Markdown text.

        content_md: the document body as Markdown; lines starting with "# "/"## " become
        headings, blank lines separate paragraphs.
        """
        return await _persist_binary(
            sink,
            format_key="pdf",
            filename=filename,
            generate=lambda: build_pdf(content_md=content_md),
            tool_name="create_pdf",
        )

    return [create_docx, create_xlsx, create_pptx, create_pdf, _make_chart_tool(sink)]


def _make_chart_tool(sink: ArtifactSink) -> BaseTool:
    @tool
    async def create_chart(filename: str, spec: dict[str, Any]) -> str:
        """Produce a downloadable chart image (.png) from a data spec.

        spec: {"type": "bar"|"line"|"pie", "labels": list of category labels, and either
        "values": list of numbers (one per label) or "series": list of {"name": str,
        "values": list}, plus optional "title"}. Example: {"type": "bar", "title":
        "Revenue", "labels": ["Q1", "Q2"], "values": [10, 14]}.
        """
        return await _persist_binary(
            sink,
            format_key="chart",
            filename=filename,
            generate=lambda: build_chart(spec=spec),
            tool_name="create_chart",
        )

    return create_chart


def make_archive_tool(sink: ArtifactSink) -> BaseTool:
    """The ``create_archive`` bundle tool — "download all files" as one .zip (§5/§14)."""

    @tool
    async def create_archive(filename: str, artifact_ids: list[str]) -> str:
        """Bundle previously-created files from this run into one downloadable .zip.

        artifact_ids: the ids of files you created earlier this run (each create_* tool
        returns its artifact_id). Pass an empty list to bundle EVERYTHING produced so far
        ("download all files"). Only files from this run are included.
        """
        members = await sink.load_members(artifact_ids)
        if not members:
            return "refused: no files from this run are available to archive"
        return await _persist_binary(
            sink,
            format_key="archive",
            filename=filename,
            generate=lambda: build_archive(members),
            tool_name="create_archive",
        )

    return create_archive


def make_image_tools(sink: ArtifactSink) -> list[BaseTool]:
    """The image tools granted by the ``image_gen`` capability (§13)."""

    @tool
    async def create_image(filename: str, spec: dict[str, Any]) -> str:
        """Produce a downloadable generated image (.png) from a spec.

        spec: {"width": int, "height": int, "background": [r,g,b] or "#rrggbb", "text":
        str, "text_color": [r,g,b] or "#rrggbb"}. v1 renders a titled banner image
        (programmatic, not an AI model).
        """
        return await _persist_binary(
            sink,
            format_key="image",
            filename=filename,
            generate=lambda: build_image(spec=spec),
            tool_name="create_image",
        )

    return [create_image, _make_chart_tool(sink)]


def assemble_producer_tools(
    sink: ArtifactSink, *, doc_chart: bool, image_gen: bool
) -> list[BaseTool]:
    """Assemble the producer's tools from its agent's capabilities (§13).

    ``doc_chart`` → text tools + office/chart tools; ``image_gen`` → image (+ chart).
    De-duplicated by tool name so ``create_chart`` (granted by both) appears once. A
    producer with neither still gets the text tools (it *is* the designated producer).
    """
    tools: list[BaseTool] = list(make_artifact_tools(sink))  # always: code/markdown/json/csv
    tools.append(make_archive_tool(sink))  # always: bundle meta-tool ("download all files")
    if doc_chart:
        tools += make_office_tools(sink)
    if image_gen:
        tools += make_image_tools(sink)
    seen: set[str] = set()
    unique: list[BaseTool] = []
    for tool_obj in tools:
        if tool_obj.name in seen:
            continue
        seen.add(tool_obj.name)
        unique.append(tool_obj)
    return unique
