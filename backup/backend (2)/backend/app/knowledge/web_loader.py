"""URL knowledge sources — fetch + HTML→text (ITEM 2 Slice D, ARCH §10.5.1/§9.4).

Turns ``kind='url'`` sources into documents. The fetch is **SSRF-guarded** (reusing
:func:`app.models_layer.validation.validate_base_url`, §9.4): the host is resolved
and rejected if it points at a loopback/private/link-local address, and every
redirect hop is re-validated so a public URL can't 302 into the internal network.

The fetched bytes are then routed back through the **universal registry**
(:func:`app.knowledge.loaders.load_file_bytes`) by content type — so an HTML page
goes through the bs4 extractor below, a linked PDF through the Slice-B PDF loader,
etc. "Ingest any URL", reusing everything already built.
"""

from __future__ import annotations

import logging
import mimetypes

import httpx
from bs4 import BeautifulSoup
from langchain_core.documents import Document

from app.knowledge.loaders import LoadContext, load_file_bytes, register_file_loader
from app.models_layer.validation import SSRFBlocked, validate_base_url

logger = logging.getLogger(__name__)

# Defensive fetch limits (R5: never trust external data / fail fast).
_FETCH_TIMEOUT_S = 20.0
_MAX_REDIRECTS = 5
_MAX_FETCH_BYTES = 10 * 1024 * 1024  # 10 MB cap on a fetched page/document
_USER_AGENT = "NEX-AGI-KnowledgeBot/1.0 (+https://nexagi.local)"

# Stripped before text extraction — non-content elements that pollute RAG chunks.
_HTML_NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "head")


def html_to_text(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """HTML bytes → one clean-text document (bs4, noise tags stripped).

    Registered for ``html``/``htm`` so it overrides the plain-text loader: a page's
    markup, scripts and styles are dropped, leaving readable text for chunking.
    """
    soup = BeautifulSoup(data, "lxml")
    # Capture the title before stripping <head> (which contains it).
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    for tag in soup(_HTML_NOISE_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    meta: dict[str, object] = {"filename": filename}
    if title:
        meta["title"] = title
        text = f"{title}\n\n{text}"
    return [Document(page_content=text, metadata=meta)] if text.strip() else []


def _filename_for(content_type: str, url: str) -> str:
    """Derive a registry-routable filename from a response's content type.

    The extension is what the universal registry dispatches on, so map the MIME type
    to one (``text/html`` → ``page.html`` → bs4 loader; ``application/pdf`` →
    ``page.pdf`` → the PDF loader; …). Defaults to ``.html`` — the common URL case.
    """
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    ext = mimetypes.guess_extension(ctype) if ctype else None
    if ext in (None, ".htm"):
        ext = ".html" if (not ctype or ctype.startswith("text/html")) else (ext or ".html")
    return f"page{ext}"


def fetch_url(url: str, *, allow_private: bool = False) -> tuple[bytes, str]:
    """Fetch a URL with SSRF protection on every hop. Returns ``(bytes, content_type)``.

    Redirects are followed manually so each ``Location`` is SSRF-validated before the
    next request — auto-following would let a public URL redirect into a private host.

    Raises:
        SSRFBlocked: a (possibly redirected) URL resolves to a non-public address.
        httpx.HTTPError: network/HTTP failure (surfaced to the worker as ``failed``).
        ValueError: the response exceeds the size cap.
    """
    current = url
    with httpx.Client(
        follow_redirects=False, timeout=_FETCH_TIMEOUT_S, headers={"User-Agent": _USER_AGENT}
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            validate_base_url(current, allow_private=allow_private)  # SSRF per hop
            resp = client.get(current)
            if resp.is_redirect and resp.has_redirect_location:
                nxt = resp.next_request
                current = str(nxt.url) if nxt else resp.headers["location"]
                continue
            resp.raise_for_status()
            if len(resp.content) > _MAX_FETCH_BYTES:
                raise ValueError(f"fetched content exceeds {_MAX_FETCH_BYTES}-byte cap: {url}")
            return resp.content, resp.headers.get("content-type", "")
    raise SSRFBlocked(url, f"too many redirects (> {_MAX_REDIRECTS})")


def load_url_documents(url: str, *, allow_private: bool, ctx: LoadContext) -> list[Document]:
    """Fetch ``url`` and route its bytes through the universal registry by content type."""
    data, content_type = fetch_url(url, allow_private=allow_private)
    filename = _filename_for(content_type, url)
    docs = load_file_bytes(data, filename, ctx)
    # Tag provenance: where each chunk came from (handy in retrieval results).
    return [
        Document(page_content=d.page_content, metadata={**d.metadata, "source_url": url})
        for d in docs
    ]


def register_html_loader() -> None:
    """Register the bs4 HTML→text loader on the universal registry (idempotent)."""
    register_file_loader("html", html_to_text)
    register_file_loader("htm", html_to_text)


register_html_loader()
