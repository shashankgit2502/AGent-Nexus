"""Unit tests for the office-format loaders (ITEM 2 Slice B, ARCH §10.5.1).

Generates real pdf/docx/xlsx/pptx bytes with the pinned libraries and runs them
through the universal registry (``load_file_bytes``) — proving the Slice-A seam
picks up the Slice-B loaders by extension, and that text/tables/rows/slides are
extracted with provenance metadata (page/sheet/slide).
"""

from __future__ import annotations

import io

from docx import Document as DocxDocument
from openpyxl import Workbook
from pptx import Presentation

from app.knowledge.loaders import load_file_bytes, supported_file_formats

# A minimal valid PDF with one text line (pypdf rebuilds the xref and extracts it).
# Assembled from short literals so the source stays within line length while the
# resulting bytes are exactly a parseable single-page text PDF.
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 52>>stream\n"
    b"BT /F1 24 Tf 72 700 Td (Hello PDF extraction test) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R/Size 6>>\n"
    b"startxref\n0\n%%EOF"
)


def test_office_formats_are_registered() -> None:
    assert {"pdf", "docx", "xlsx", "xlsm", "pptx"} <= supported_file_formats()


def test_pdf_extracts_text_per_page() -> None:
    docs = load_file_bytes(_MINIMAL_PDF, "report.pdf")
    assert "Hello PDF extraction test" in docs[0].page_content
    assert docs[0].metadata["page"] == 1


def test_docx_extracts_paragraphs_and_tables() -> None:
    d = DocxDocument()
    d.add_paragraph("Executive summary paragraph.")
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Revenue"
    table.rows[0].cells[1].text = "42"
    buf = io.BytesIO()
    d.save(buf)

    docs = load_file_bytes(buf.getvalue(), "doc.docx")
    body = docs[0].page_content
    assert "Executive summary paragraph." in body
    assert "Revenue | 42" in body  # table cells preserved


def test_xlsx_extracts_one_document_per_row_with_sheet_meta() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "People"
    ws.append(["name", "role"])
    ws.append(["Ada", "engineer"])
    ws.append(["Grace", "scientist"])
    buf = io.BytesIO()
    wb.save(buf)

    docs = load_file_bytes(buf.getvalue(), "people.xlsx")
    assert len(docs) == 2
    assert "name: Ada" in docs[0].page_content and "role: engineer" in docs[0].page_content
    assert docs[0].metadata["sheet"] == "People"
    assert docs[1].metadata["row"] == 3


def test_pptx_extracts_one_document_per_slide() -> None:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # "Title Only"
    slide.shapes.title.text = "Quarterly roadmap"
    buf = io.BytesIO()
    prs.save(buf)

    docs = load_file_bytes(buf.getvalue(), "deck.pptx")
    assert "Quarterly roadmap" in docs[0].page_content
    assert docs[0].metadata["slide"] == 1
