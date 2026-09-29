"""Unit tests for the URL knowledge loader (ITEM 2 Slice D).

Offline: HTML→text extraction, content-type→filename routing, the SSRF guard
(rejects private hosts before any network call), and end-to-end routing of fetched
bytes through the universal registry (via a stubbed ``fetch_url``).
"""

from __future__ import annotations

import pytest

from app.knowledge import web_loader
from app.knowledge.loaders import LoadContext, load_file_bytes
from app.models_layer.validation import SSRFBlocked

_HTML = (
    b"<html><head><title>Quarterly Report</title><style>x{}</style></head>"
    b"<body><h1>Revenue</h1><p>Up 20% YoY.</p><script>track()</script></body></html>"
)


def test_html_loader_strips_noise_and_keeps_title() -> None:
    docs = load_file_bytes(_HTML, "page.html", LoadContext())
    content = docs[0].page_content
    assert "Quarterly Report" in content  # title prepended
    assert "Up 20% YoY." in content
    assert "track()" not in content  # script stripped
    assert docs[0].metadata["title"] == "Quarterly Report"


def test_filename_for_content_type_routes_by_mime() -> None:
    assert web_loader._filename_for("text/html; charset=utf-8", "http://x") == "page.html"
    assert web_loader._filename_for("application/pdf", "http://x") == "page.pdf"
    assert web_loader._filename_for("", "http://x") == "page.html"  # default


def test_fetch_url_blocks_private_host_before_request() -> None:
    # SSRF guard runs before any network I/O — a loopback URL is rejected outright.
    with pytest.raises(SSRFBlocked):
        web_loader.fetch_url("http://127.0.0.1/admin", allow_private=False)


def test_load_url_routes_fetched_bytes_through_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub the network: an HTML page is fetched, then routed through the bs4 loader,
    # and each chunk is tagged with its source_url.
    monkeypatch.setattr(
        web_loader, "fetch_url", lambda url, *, allow_private=False: (_HTML, "text/html")
    )
    docs = web_loader.load_url_documents(
        "https://example.com/report", allow_private=False, ctx=LoadContext()
    )
    assert "Up 20% YoY." in docs[0].page_content
    assert docs[0].metadata["source_url"] == "https://example.com/report"


def test_load_url_routes_fetched_pdf_bytes_to_pdf_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    # A URL serving a PDF reuses the Slice-B PDF loader — "ingest any URL".
    pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 40>>stream\nBT /F1 18 Tf 72 700 Td (URL PDF body) Tj ET\n"
        b"endstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"trailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF"
    )
    monkeypatch.setattr(
        web_loader, "fetch_url", lambda url, *, allow_private=False: (pdf, "application/pdf")
    )
    docs = web_loader.load_url_documents(
        "https://example.com/doc.pdf", allow_private=False, ctx=LoadContext()
    )
    assert "URL PDF body" in docs[0].page_content
