"""Office-document loaders — pdf / docx / xlsx / pptx (ITEM 2 Slice B, ARCH §10.5.1).

Specialized, high-fidelity extractors for the common office formats, registered
against the universal loader registry (:func:`app.knowledge.loaders.register_file_loader`)
so the worker picks them up with no changes — the registry seam doing its job.

Each loader takes raw bytes + filename and returns ``Document`` s (one per natural
unit — PDF page, spreadsheet row, slide — so provenance survives chunking). All the
underlying libraries read from an in-memory stream, so no temp file is written.

Pinned + R1-verified (2026-06-21): ``pypdf==6.13.3``, ``python-docx==1.2.0``,
``openpyxl==3.1.5``, ``python-pptx==1.0.2``. Scanned/image-only documents (no text
layer) extract no text and surface as ``EmptyDocument`` → ``failed`` until Slice C
adds OCR / vision-model captioning; legacy ``.doc/.xls/.ppt`` and the long tail are
Slice D (``unstructured``). Honest degradation, never a silent hang (R3).
"""

from __future__ import annotations

import io
import logging

from docx import Document as DocxDocument
from langchain_core.documents import Document
from openpyxl import load_workbook
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pypdf import PdfReader

from app.knowledge.loaders import LoadContext, image_text_from, register_file_loader

logger = logging.getLogger(__name__)


def _image_doc(
    data: bytes, mime: str, ctx: LoadContext, *, filename: str, **meta: object
) -> Document | None:
    """Caption/OCR one embedded image → a Document, or None if nothing extracted.

    Embedded-image enrichment is best-effort: a single image's caption failure is
    **logged** (not swallowed silently — R3) and skipped, because the document's
    text is the primary content and shouldn't fail over one figure. A standalone
    image (image_loaders) takes the opposite stance and surfaces the error.
    """
    if ctx.caption_image is None and ctx.ocr_image is None:
        return None
    try:
        text = image_text_from(data, mime, ctx)
    except Exception:  # noqa: BLE001 — logged with context, then skipped (best-effort)
        logger.warning("embedded image enrichment failed in %s", filename, exc_info=True)
        return None
    if not text.strip():
        return None
    return Document(page_content=text, metadata={"filename": filename, "image": True, **meta})


def _load_pdf(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """PDF → one document per page (text layer) + captioned embedded images (Slice C)."""
    reader = PdfReader(io.BytesIO(data))
    docs: list[Document] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            docs.append(
                Document(page_content=text, metadata={"filename": filename, "page": page_no})
            )
        for image in page.images:
            doc = _image_doc(
                image.data, "image/png", ctx, filename=filename, page=page_no, name=image.name
            )
            if doc is not None:
                docs.append(doc)
    return docs


def _load_docx(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """DOCX → text (paragraphs + tables) + captioned embedded images (Slice C)."""
    doc = DocxDocument(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    body = "\n".join(parts)
    docs = [Document(page_content=body, metadata={"filename": filename})] if body.strip() else []
    # Embedded images live in the docx package relationships (reltype …/image).
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            blob = rel.target_part.blob
            mime = getattr(rel.target_part, "content_type", "image/png")
            image_doc = _image_doc(blob, mime, ctx, filename=filename)
            if image_doc is not None:
                docs.append(image_doc)
    return docs


def _load_xlsx(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """XLSX → one document per non-empty row, rendered ``header: value`` per sheet.

    ``data_only=True`` returns computed values (not formulas); ``read_only=True``
    streams large workbooks without loading them whole.
    """
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    docs: list[Document] = []
    try:
        for sheet in wb.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(header or ())]
            for r_idx, row in enumerate(rows, start=2):
                pairs = [
                    f"{headers[i] if i < len(headers) else f'col{i}'}: {v}"
                    for i, v in enumerate(row)
                    if v not in (None, "")
                ]
                if pairs:
                    docs.append(
                        Document(
                            page_content="\n".join(pairs),
                            metadata={"filename": filename, "sheet": sheet.title, "row": r_idx},
                        )
                    )
    finally:
        wb.close()
    return docs


def _load_pptx(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """PPTX → one document per slide (shape text) + captioned picture shapes (Slice C)."""
    prs = Presentation(io.BytesIO(data))
    docs: list[Document] = []
    for slide_no, slide in enumerate(prs.slides, start=1):
        texts = [
            shape.text.strip()
            for shape in slide.shapes
            if shape.has_text_frame and shape.text.strip()
        ]
        if texts:
            docs.append(
                Document(
                    page_content="\n".join(texts),
                    metadata={"filename": filename, "slide": slide_no},
                )
            )
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                image = shape.image
                doc = _image_doc(
                    image.blob, image.content_type, ctx, filename=filename, slide=slide_no
                )
                if doc is not None:
                    docs.append(doc)
    return docs


# Register against the universal registry — the worker resolves these by extension
# with no further wiring (the Slice-A seam). Last-wins, so this overrides any
# placeholder. Legacy single-binary formats (.doc/.xls/.ppt) are intentionally left
# for Slice D's `unstructured`/libreoffice path.
def register_office_loaders() -> None:
    """Register the office loaders on the universal registry (idempotent)."""
    register_file_loader("pdf", _load_pdf)
    register_file_loader("docx", _load_docx)
    register_file_loader("xlsx", _load_xlsx)
    register_file_loader("xlsm", _load_xlsx)
    register_file_loader("pptx", _load_pptx)


register_office_loaders()
