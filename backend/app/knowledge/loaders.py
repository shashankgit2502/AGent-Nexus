"""Universal document loaders — bytes/URI → ``Document`` list (ARCH §10.5.1).

The "ingest anything" layer. A source is routed to a loader by its **kind** and,
for files, by **file format** (extension + MIME, not trusted blindly). The goal is
the chat-app experience: drop any document and get text out.

Architecture — a registry, not a hand-wired switch
--------------------------------------------------
:data:`_FILE_LOADERS` maps a normalized format key to a loader callable. Slice A
wires the **native, no-dependency** formats (plain text / markdown / code / csv /
json) plus an inline ``team_doc``. Later slices register more formats against the
**same** registry without touching the worker:

* Slice B — office formats (pdf, docx, xlsx, pptx) via pinned, R1-verified deps.
* Slice C — images + embedded images, captioned through a vision catalog model.
* Slice D — the ``unstructured`` long-tail backbone + url fetch + db connector.

A format with no registered loader raises :class:`UnsupportedFileFormat`, which the
worker turns into ``status='failed'`` with a precise reason — never a silent hang,
never a guess (R3). This degradation is also how a dev box without the Slice-B/C
system binaries behaves honestly until they are installed.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document


@dataclass(frozen=True)
class LoadContext:
    """Optional enrichment services available to loaders (ITEM 2 Slice C).

    Threaded from the worker to every loader so image-aware loaders (standalone
    images, embedded images in office docs) can caption/OCR without coupling the
    loader layer to the model-resolution layer. ``None`` for a service means the
    capability is disabled (e.g. no vision model configured, OCR binary missing) —
    loaders degrade gracefully (skip images / surface a clear failure), never crash.

    * ``caption_image(image_bytes, mime_type) -> str`` — vision-model description.
    * ``ocr_image(image_bytes) -> str`` — tesseract OCR text.
    """

    caption_image: Callable[[bytes, str], str] | None = None
    ocr_image: Callable[[bytes], str] | None = None


# A loader takes the file's raw bytes, its filename, and the load context.
FileLoader = Callable[[bytes, str, LoadContext], list[Document]]


class UnsupportedSourceKind(NotImplementedError):
    """A knowledge source *kind* (url/db) has no loader wired in this build slice."""


class UnsupportedFileFormat(NotImplementedError):
    """A file's format has no registered loader yet (e.g. pdf before Slice B)."""

    def __init__(self, fmt: str, filename: str) -> None:
        super().__init__(f"file format {fmt!r} ({filename!r}) is not yet supported for ingestion")
        self.fmt = fmt
        self.filename = filename


class EmptyDocument(ValueError):
    """A source produced no extractable text (e.g. an empty or unreadable file)."""


# ── Native loaders (no extra deps) ─────────────────────────────────────────────
def _decode_text(data: bytes) -> str:
    """Decode bytes to text, tolerating non-UTF-8 inputs (best-effort, lossless-ish).

    UTF-8 first (the common case); on failure fall back to latin-1, which maps every
    byte to a code point so we never crash on an unknown encoding. Slice B swaps in
    proper charset detection (``charset-normalizer``); for the native text family
    this keeps Slice A dependency-free without silently dropping content.
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _load_text(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """Plain text / markdown / code: the whole file as one document (pre-split)."""
    content = _decode_text(data)
    return [Document(page_content=content, metadata={"filename": filename})]


def _load_csv(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """CSV → one document per row, rendered ``col: value`` so columns survive chunking."""
    text = _decode_text(data)
    reader = csv.DictReader(io.StringIO(text))
    docs: list[Document] = []
    for i, row in enumerate(reader):
        rendered = "\n".join(f"{k}: {v}" for k, v in row.items() if v not in (None, ""))
        if rendered:
            docs.append(Document(page_content=rendered, metadata={"filename": filename, "row": i}))
    if not docs:  # header-only or empty CSV — fall back to the raw text
        return _load_text(data, filename, ctx)
    return docs


def _load_json(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """JSON → pretty-printed text (stable key order) so structure is searchable."""
    try:
        parsed = json.loads(_decode_text(data))
    except json.JSONDecodeError:
        return _load_text(data, filename, ctx)  # malformed → treat as text, don't fail
    pretty = json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True)
    return [Document(page_content=pretty, metadata={"filename": filename})]


# Format key → loader. Slices B/C/D extend this map via :func:`register_file_loader`.
# Keys are lowercase, dot-less extensions.
_TEXT_EXTS = (
    "txt",
    "md",
    "markdown",
    "rst",
    "log",
    "text",
    # common code/config formats — plain text is the right extraction
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "java",
    "go",
    "rs",
    "rb",
    "php",
    "c",
    "h",
    "cpp",
    "hpp",
    "cs",
    "kt",
    "swift",
    "sh",
    "bash",
    "sql",
    "html",
    "htm",
    "css",
    "scss",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "env",
    "xml",
)
_FILE_LOADERS: dict[str, FileLoader] = {
    **{ext: _load_text for ext in _TEXT_EXTS},
    "csv": _load_csv,
    "tsv": _load_csv,
    "json": _load_json,
    "jsonl": _load_text,
}


def register_file_loader(fmt: str, loader: FileLoader) -> None:
    """Register a loader for a file format (extension key). Used by later slices.

    Idempotent-overwrite by design (last registration wins), so a slice can replace
    a placeholder loader with a higher-fidelity one.
    """
    _FILE_LOADERS[fmt.lower().lstrip(".")] = loader


def supported_file_formats() -> frozenset[str]:
    """The set of currently-registered file-format keys (for diagnostics/tests)."""
    return frozenset(_FILE_LOADERS)


def _format_key(filename: str) -> str:
    """Normalized format key from a filename's extension (lowercase, no dot)."""
    return Path(filename).suffix.lower().lstrip(".")


def image_text_from(data: bytes, mime: str, ctx: LoadContext) -> str:
    """Extract text from an image via the context's vision caption + OCR (Slice C).

    Runs whichever services the context provides and concatenates their output
    (caption first, then OCR). Returns ``""`` when no service is configured or both
    yield nothing. Exceptions propagate — callers decide whether an image that *is*
    the document (standalone image) should fail the source, or whether an embedded
    image should be logged-and-skipped (office loaders).
    """
    parts: list[str] = []
    if ctx.caption_image is not None:
        caption = ctx.caption_image(data, mime).strip()
        if caption:
            parts.append(caption)
    if ctx.ocr_image is not None:
        ocr = ctx.ocr_image(data).strip()
        if ocr:
            parts.append(f"Text in image: {ocr}")
    return "\n\n".join(parts)


def load_file_bytes(data: bytes, filename: str, ctx: LoadContext | None = None) -> list[Document]:
    """Route a file's bytes to its format loader (the registry dispatch).

    ``ctx`` carries optional vision/OCR services (Slice C); defaults to an empty
    context (no enrichment) so text-format callers and tests are unaffected.

    Raises:
        UnsupportedFileFormat: no loader registered for the file's extension.
        EmptyDocument: the loader produced no extractable text.
    """
    ctx = ctx or LoadContext()
    fmt = _format_key(filename)
    loader = _FILE_LOADERS.get(fmt)
    if loader is None:
        raise UnsupportedFileFormat(fmt or "unknown", filename)
    docs = [d for d in loader(data, filename, ctx) if d.page_content.strip()]
    if not docs:
        raise EmptyDocument(f"{filename!r} produced no extractable text")
    return docs


def load_source_documents(
    kind: str,
    *,
    uri: str | None = None,
    text: str | None = None,
    ctx: LoadContext | None = None,
    allow_private: bool = False,
) -> list[Document]:
    """Load one knowledge source into raw documents (pre-split), per kind (§10.5.1).

    * ``team_doc`` — inline ``text`` (no file).
    * ``file`` — read the bytes at ``uri`` (object-storage path) and route by format.
    * ``url`` — fetch ``uri`` (SSRF-guarded) and route its bytes by content type (Slice D).
    * ``db`` — handled by the worker's connector (not here).

    ``ctx`` (Slice C) carries optional vision/OCR enrichment passed to file loaders.
    ``allow_private`` (Slice D) permits fetching loopback/private hosts — local dev only.

    Raises:
        ValueError: required ``uri``/``text`` missing for the kind.
        UnsupportedSourceKind: an unknown kind (``db`` is loaded by the worker).
        UnsupportedFileFormat / EmptyDocument: file routing failures.
    """
    if kind == "team_doc":
        if text is None:
            raise ValueError("kind='team_doc' requires inline 'text'")
        if not text.strip():
            raise EmptyDocument("team_doc text is empty")
        return [Document(page_content=text)]
    if kind == "file":
        if uri is None:
            raise ValueError("kind='file' requires a 'uri' (object-storage path)")
        data = Path(uri).read_bytes()
        return load_file_bytes(data, Path(uri).name, ctx or LoadContext())
    if kind == "url":
        if uri is None:
            raise ValueError("kind='url' requires a 'uri'")
        # Lazy import: web_loader imports from this module (avoid a circular import).
        from app.knowledge.web_loader import load_url_documents

        return load_url_documents(uri, allow_private=allow_private, ctx=ctx or LoadContext())
    raise UnsupportedSourceKind(f"knowledge source kind {kind!r} has no loader")
