"""Office + media byte generators (ARTIFACTS.md §5, Slice 4).

Pure functions turning a validated spec into file **bytes** — one per format. They are
CPU-bound and synchronous; the tools call them through ``asyncio.to_thread`` so heavy
generation never blocks the event loop (the same offload the knowledge worker uses).

Libraries (R1, verified + pinned at install): ``python-docx`` 1.2, ``openpyxl`` 3.1,
``python-pptx`` 1.0, ``fpdf2`` 2.8 (PDF), ``matplotlib`` 3.11 (charts), ``Pillow`` 12
(images). Heavy libs are **lazily imported** inside each function so importing this
module (at app startup) stays cheap and a format's dependency only loads when used.

Charts use matplotlib's **object-oriented** API (``Figure`` + ``FigureCanvasAgg``), not
the global ``pyplot`` state machine, so concurrent generation across worker threads is
safe. Every function validates its spec and raises ``ValueError`` on malformed input
(the tool turns that into a refusal the agent can correct — R3/R5).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

# ── MIME / extension registry (the binary kinds, §2) ──────────────────────────
_OOXML = "application/vnd.openxmlformats-officedocument"
BINARY_FORMATS: dict[str, tuple[str, str, str]] = {
    # format_key: (artifact_kind, mime_type, extension)
    "docx": ("docx", f"{_OOXML}.wordprocessingml.document", ".docx"),
    "xlsx": ("xlsx", f"{_OOXML}.spreadsheetml.sheet", ".xlsx"),
    "pptx": ("pptx", f"{_OOXML}.presentationml.presentation", ".pptx"),
    "pdf": ("pdf", "application/pdf", ".pdf"),
    "chart": ("image", "image/png", ".png"),
    "image": ("image", "image/png", ".png"),
    "archive": ("archive", "application/zip", ".zip"),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def build_docx(*, title: str, sections: list[dict[str, Any]]) -> bytes:
    """Word document: a title + sections (each an optional heading + body text)."""
    from docx import Document

    _require(isinstance(sections, list), "docx 'sections' must be a list")
    document = Document()
    if title:
        document.add_heading(str(title), level=0)
    for section in sections:
        _require(isinstance(section, dict), "each docx section must be an object")
        heading = section.get("heading")
        if heading:
            document.add_heading(str(heading), level=1)
        body = section.get("body")
        if body:
            for paragraph in str(body).split("\n\n"):
                document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_xlsx(*, sheets: list[dict[str, Any]]) -> bytes:
    """Excel workbook: sheets of rows; a cell string starting ``=`` is a formula."""
    from openpyxl import Workbook

    _require(isinstance(sheets, list) and len(sheets) > 0, "xlsx 'sheets' must be a non-empty list")
    workbook = Workbook()
    workbook.remove(workbook.active)  # drop the default sheet; add our own
    for index, sheet in enumerate(sheets):
        _require(isinstance(sheet, dict), "each xlsx sheet must be an object")
        name = str(sheet.get("name") or f"Sheet{index + 1}")[:31]  # Excel caps sheet names at 31
        worksheet = workbook.create_sheet(title=name)
        rows = sheet.get("rows") or []
        _require(isinstance(rows, list), "xlsx sheet 'rows' must be a list of lists")
        for row in rows:
            _require(isinstance(row, list), "each xlsx row must be a list of cells")
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_pptx(*, slides: list[dict[str, Any]]) -> bytes:
    """PowerPoint: slides each with a title + bullet points."""
    from pptx import Presentation

    _require(isinstance(slides, list) and len(slides) > 0, "pptx 'slides' must be a non-empty list")
    presentation = Presentation()
    bullet_layout = presentation.slide_layouts[1]  # "Title and Content"
    for slide_spec in slides:
        _require(isinstance(slide_spec, dict), "each pptx slide must be an object")
        slide = presentation.slides.add_slide(bullet_layout)
        slide.shapes.title.text = str(slide_spec.get("title") or "")
        bullets = slide_spec.get("bullets") or []
        _require(isinstance(bullets, list), "pptx slide 'bullets' must be a list")
        body = slide.placeholders[1].text_frame
        body.clear()
        for i, bullet in enumerate(bullets):
            paragraph = body.paragraphs[0] if i == 0 else body.add_paragraph()
            paragraph.text = str(bullet)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def build_pdf(*, content_md: str) -> bytes:
    """PDF rendered from markdown-ish text (headings via ``#``; paragraphs wrap)."""
    from fpdf import FPDF

    _require(
        isinstance(content_md, str) and content_md.strip() != "", "pdf 'content_md' is required"
    )
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    for line in content_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            pdf.set_font("Helvetica", style="B", size=18)
            pdf.multi_cell(0, 9, stripped[2:])
        elif stripped.startswith("## "):
            pdf.set_font("Helvetica", style="B", size=14)
            pdf.multi_cell(0, 8, stripped[3:])
        elif stripped == "":
            pdf.ln(4)
        else:
            pdf.set_font("Helvetica", size=11)
            # latin-1 fallback: the core fonts are latin-1; drop unencodable glyphs.
            pdf.multi_cell(0, 6, stripped.encode("latin-1", "replace").decode("latin-1"))
    return bytes(pdf.output())


def build_chart(*, spec: dict[str, Any]) -> bytes:
    """Chart PNG from a data spec: ``{type: bar|line|pie, labels, values|series, title?}``."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    _require(isinstance(spec, dict), "chart 'spec' must be an object")
    chart_type = str(spec.get("type") or "bar").lower()
    labels = spec.get("labels") or []
    _require(
        isinstance(labels, list) and len(labels) > 0, "chart 'labels' must be a non-empty list"
    )
    # Accept either a flat `values` or a `series` of {name, values}.
    series = spec.get("series")
    if not series:
        values = spec.get("values") or []
        _require(isinstance(values, list), "chart 'values' must be a list")
        series = [{"name": spec.get("series_name") or "", "values": values}]
    _require(
        isinstance(series, list) and len(series) > 0, "chart 'series' must be a non-empty list"
    )

    figure = Figure(figsize=(7, 4.5), dpi=120)
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    str_labels = [str(label) for label in labels]
    if chart_type == "pie":
        first = series[0].get("values") or []
        axes.pie(first, labels=str_labels, autopct="%1.1f%%")
    else:
        for one in series:
            values = one.get("values") or []
            _require(len(values) == len(labels), "each series must have one value per label")
            if chart_type == "line":
                axes.plot(str_labels, values, marker="o", label=str(one.get("name") or ""))
            else:  # bar (default)
                axes.bar(str_labels, values, label=str(one.get("name") or ""))
        if any(one.get("name") for one in series):
            axes.legend()
    if spec.get("title"):
        axes.set_title(str(spec["title"]))
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    return buffer.getvalue()


def build_image(*, spec: dict[str, Any]) -> bytes:
    """A programmatically generated PNG (titled banner) from a spec (no AI model, v1)."""
    from PIL import Image, ImageDraw

    _require(isinstance(spec, dict), "image 'spec' must be an object")
    width = int(spec.get("width") or 1024)
    height = int(spec.get("height") or 512)
    _require(0 < width <= 4096 and 0 < height <= 4096, "image dimensions must be within 1..4096")
    background = _color(spec.get("background"), (17, 17, 19))
    text_color = _color(spec.get("text_color"), (16, 185, 129))
    image = Image.new("RGB", (width, height), background)
    text = str(spec.get("text") or "")
    if text:
        draw = ImageDraw.Draw(image)
        draw.text((width // 20, height // 2 - 12), text, fill=text_color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _unique_name(name: str, seen: dict[str, int]) -> str:
    """De-duplicate member names so two ``main.py`` files don't collide in the zip."""
    if name not in seen:
        seen[name] = 0
        return name
    seen[name] += 1
    path = Path(name)
    return f"{path.stem}_{seen[name]}{path.suffix}"


def build_archive(members: list[tuple[str, bytes]]) -> bytes:
    """Bundle ``(filename, bytes)`` members into a deflated ``.zip`` (§5/§14).

    The "download all files" deliverable. Duplicate member names are disambiguated so
    every file lands in the archive. Raises ``ValueError`` if there is nothing to bundle.
    """
    _require(len(members) > 0, "create_archive needs at least one artifact to bundle")
    buffer = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for raw_name, data in members:
            archive.writestr(_unique_name(raw_name or "artifact", seen), data)
    return buffer.getvalue()


def _color(value: Any, default: tuple[int, int, int]) -> tuple[int, int, int]:
    """Parse ``[r,g,b]`` / ``#rrggbb`` into an RGB tuple, falling back to ``default``."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    return default
