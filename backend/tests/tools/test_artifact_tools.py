"""Unit tests for the text/code artifact tools (ARTIFACTS.md §5, Slice 2).

Drives the tools against a recording fake sink (no DB) to prove boundary validation
(§15 allowlist + JSON well-formedness), the persist→ref path, and that a refusal is a
returned observation the agent can act on — never a raised crash (R3).
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.tools import BaseTool

from app.artifacts.descriptor import ArtifactRef
from app.artifacts.service import ArtifactTooLarge
from app.tools.artifacts import make_artifact_tools


class _FakeSink:
    """Records ``write_text`` calls; optionally simulates the size-cap refusal."""

    def __init__(self, *, raise_too_large: bool = False) -> None:
        self.writes: list[dict[str, str]] = []
        self._raise = raise_too_large

    async def write_text(
        self,
        *,
        kind: str,
        filename: str,
        mime_type: str,
        content: str,
        content_format: str,
        tool: str,
    ) -> ArtifactRef:
        if self._raise:
            raise ArtifactTooLarge("artifact too large")
        self.writes.append(
            {"kind": kind, "filename": filename, "mime_type": mime_type, "tool": tool}
        )
        return ArtifactRef(
            artifact_id=uuid4(),
            kind=kind,
            filename=filename,
            download_url="/artifacts/x/download?token=t",
        )


def _tool(tools: list[BaseTool], name: str) -> BaseTool:
    return next(t for t in tools if t.name == name)


async def test_write_code_file_persists_and_returns_ref() -> None:
    sink = _FakeSink()
    tool = _tool(make_artifact_tools(sink), "write_code_file")  # type: ignore[arg-type]
    out = await tool.ainvoke(
        {"filename": "main.py", "language": "python", "content": "print('hi')"}
    )
    assert "artifact_id=" in out and "main.py" in out
    assert sink.writes[0]["kind"] == "code"
    assert sink.writes[0]["mime_type"] == "text/x-python"


async def test_write_code_file_rejects_unsupported_extension() -> None:
    sink = _FakeSink()
    tool = _tool(make_artifact_tools(sink), "write_code_file")  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "evil.exe", "language": "python", "content": "x"})
    assert out.startswith("refused")
    assert sink.writes == []


async def test_write_json_rejects_invalid_json() -> None:
    sink = _FakeSink()
    tool = _tool(make_artifact_tools(sink), "write_json")  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "data.json", "content": "{not valid"})
    assert out.startswith("refused")
    assert sink.writes == []


async def test_write_json_accepts_valid_json() -> None:
    sink = _FakeSink()
    tool = _tool(make_artifact_tools(sink), "write_json")  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "data.json", "content": '{"a": 1}'})
    assert "data.json" in out
    assert sink.writes[0]["kind"] == "json"


async def test_write_markdown_requires_md_extension() -> None:
    sink = _FakeSink()
    tool = _tool(make_artifact_tools(sink), "write_markdown")  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "notes.txt", "content": "# hi"})
    assert out.startswith("refused")
    assert sink.writes == []


async def test_oversize_is_refused_not_raised() -> None:
    sink = _FakeSink(raise_too_large=True)
    tool = _tool(make_artifact_tools(sink), "write_markdown")  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "x.md", "content": "hi"})
    assert out.startswith("refused")
