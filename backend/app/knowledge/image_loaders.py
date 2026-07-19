"""Standalone image-file loaders — png/jpg/… (ITEM 2 Slice C, ARCH §10.5.1).

Registers image formats on the universal registry. An image *is* its document, so
the loader turns the bytes into searchable text via the load context's vision
caption + OCR (:func:`app.knowledge.loaders.image_text_from`). With no enrichment
configured the image yields no text → ``EmptyDocument`` → the source fails with a
clear reason (e.g. "no vision model configured") rather than silently ingesting
nothing (R3).

Pure like the other loaders: the vision model + OCR are injected by the worker
through the context; this module never touches the model layer.
"""

from __future__ import annotations

import mimetypes

from langchain_core.documents import Document

from app.knowledge.loaders import LoadContext, image_text_from, register_file_loader

# Raster image formats we accept as standalone knowledge sources.
_IMAGE_EXTS = ("png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff")


def _mime_for(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "image/png"


def _load_image(data: bytes, filename: str, ctx: LoadContext) -> list[Document]:
    """An image → one document of its vision caption + OCR text (Slice C)."""
    text = image_text_from(data, _mime_for(filename), ctx)
    if not text.strip():
        # No caption + no OCR text. Empty by design → load_file_bytes raises
        # EmptyDocument so the worker reports a precise, actionable failure.
        return []
    return [Document(page_content=text, metadata={"filename": filename, "kind": "image"})]


def register_image_loaders() -> None:
    """Register the image loaders on the universal registry (idempotent)."""
    for ext in _IMAGE_EXTS:
        register_file_loader(ext, _load_image)


register_image_loaders()


# Re-exported for the (unlikely) caller that wants the extension set.
def image_extensions() -> tuple[str, ...]:
    """The raster image extensions handled as standalone sources."""
    return _IMAGE_EXTS


__all__ = ["register_image_loaders", "image_extensions", "_load_image"]
