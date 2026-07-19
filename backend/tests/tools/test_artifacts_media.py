"""Unit tests for the office/media tools + capability assembly (ARTIFACTS §5/§13).

Drives the tools against a recording fake sink (no DB): a tool generates real bytes
(off-loop) and persists via the sink, a bad spec is refused (not raised), filenames get
the format extension, and `assemble_producer_tools` honours the §13 capability gate.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.tools import BaseTool

from app.artifacts.descriptor import ArtifactRef
from app.tools.artifacts_media import (
    assemble_producer_tools,
    make_image_tools,
    make_office_tools,
)


class _FakeBinarySink:
    """Records `write_binary` calls; also supports `write_text` (for assembly tests)."""

    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    async def write_binary(
        self, *, kind: str, filename: str, mime_type: str, data: bytes, tool: str
    ) -> ArtifactRef:
        self.writes.append(
            {
                "kind": kind,
                "filename": filename,
                "mime_type": mime_type,
                "len": len(data),
                "tool": tool,
            }
        )
        return ArtifactRef(artifact_id=uuid4(), kind=kind, filename=filename, download_url="/d")

    async def write_text(self, **_kw: object) -> ArtifactRef:  # pragma: no cover - not hit here
        return ArtifactRef(artifact_id=uuid4(), kind="code", filename="x", download_url="/d")


def _tool(tools: list[BaseTool], name: str) -> BaseTool:
    return next(t for t in tools if t.name == name)


async def test_create_docx_generates_and_persists() -> None:
    sink = _FakeBinarySink()
    tool = _tool(make_office_tools(sink), "create_docx")  # type: ignore[arg-type]
    out = await tool.ainvoke(
        {"filename": "report", "title": "T", "sections": [{"heading": "H", "body": "b"}]}
    )
    assert "artifact_id=" in out
    write = sink.writes[0]
    assert write["kind"] == "docx"
    assert write["filename"] == "report.docx"  # extension enforced
    assert int(write["len"]) > 0  # real bytes generated


async def test_create_chart_generates_png() -> None:
    sink = _FakeBinarySink()
    tool = _tool(make_office_tools(sink), "create_chart")  # type: ignore[arg-type]
    out = await tool.ainvoke(
        {"filename": "rev", "spec": {"type": "bar", "labels": ["a", "b"], "values": [1, 2]}}
    )
    assert "artifact_id=" in out
    assert sink.writes[0]["kind"] == "image"
    assert sink.writes[0]["filename"] == "rev.png"


async def test_create_xlsx_bad_spec_is_refused_not_raised() -> None:
    sink = _FakeBinarySink()
    tool = _tool(make_office_tools(sink), "create_xlsx")  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "x", "sheets": []})  # empty → ValueError → refusal
    assert out.startswith("refused")
    assert sink.writes == []


async def test_create_image_generates_png() -> None:
    sink = _FakeBinarySink()
    tool = _tool(make_image_tools(sink), "create_image")  # type: ignore[arg-type]
    out = await tool.ainvoke(
        {"filename": "banner", "spec": {"text": "hi", "width": 80, "height": 40}}
    )
    assert "artifact_id=" in out
    assert sink.writes[0]["filename"] == "banner.png"


def test_assemble_producer_tools_honours_capability_gate() -> None:
    sink = _FakeBinarySink()
    doc_only = {t.name for t in assemble_producer_tools(sink, doc_chart=True, image_gen=False)}  # type: ignore[arg-type]
    assert {
        "write_code_file",
        "create_docx",
        "create_xlsx",
        "create_pptx",
        "create_pdf",
        "create_chart",
    } <= doc_only
    assert "create_image" not in doc_only

    image_only = {t.name for t in assemble_producer_tools(sink, doc_chart=False, image_gen=True)}  # type: ignore[arg-type]
    assert "create_image" in image_only and "create_chart" in image_only
    assert "create_docx" not in image_only


def test_assemble_dedupes_chart_when_both_capabilities() -> None:
    sink = _FakeBinarySink()
    tools = assemble_producer_tools(sink, doc_chart=True, image_gen=True)  # type: ignore[arg-type]
    assert sum(1 for t in tools if t.name == "create_chart") == 1
