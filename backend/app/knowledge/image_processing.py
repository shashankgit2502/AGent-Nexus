"""Image enrichment services — vision captioning + OCR (ITEM 2 Slice C, ARCH §10.5).

The model-touching half of image ingestion. Standalone images and embedded images
in office docs are turned into searchable text by two complementary services:

* **Vision caption** — the chosen ``supports_vision`` catalog model describes the
  image (objects, charts, diagrams, layout). This is the primary path (the user's
  choice: "vision model via catalog").
* **OCR** — ``tesseract`` extracts literal text (scanned pages, screenshots). The
  fallback that catches text a caption summarizes away.

Both are wrapped as the plain callables :class:`~app.knowledge.loaders.LoadContext`
expects, so the loader layer stays decoupled from the model-resolution layer — the
worker builds the context and injects it. Each service degrades **honestly**: no
vision model configured → no captioner; tesseract binary absent → OCR raises a
clear, actionable error (surfaced as ``failed`` for a standalone image, logged-and-
skipped for an embedded one) rather than a silent blank (R3).
"""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.knowledge.loaders import LoadContext

logger = logging.getLogger(__name__)

# Kept short + deterministic: we want a dense, factual description for retrieval,
# not prose. The model sees the image as a standard v1 content block (R1-verified
# against langchain-core 1.4.7: {"type":"image","base64":..,"mime_type":..}).
_CAPTION_PROMPT = (
    "Describe this image for a search index. Include any visible text, the type of "
    "content (photo, chart, diagram, screenshot, table), and the key facts it conveys. "
    "Be concise and factual."
)


class OcrUnavailable(RuntimeError):
    """tesseract (the OCR engine binary) is not installed/!on PATH on this host."""


def make_vision_captioner(model: BaseChatModel) -> Callable[[bytes, str], str]:
    """Wrap a resolved vision chat model as a ``(image_bytes, mime) -> caption`` callable.

    The model is invoked synchronously (the worker runs this inside a thread). The
    image is passed as the langchain v1 standard image content block; the response
    text is the caption.
    """

    def caption(data: bytes, mime_type: str) -> str:
        block = {
            "type": "image",
            "base64": base64.b64encode(data).decode("ascii"),
            "mime_type": mime_type or "image/png",
        }
        message = HumanMessage(content=[{"type": "text", "text": _CAPTION_PROMPT}, block])
        result = model.invoke([message])
        text = result.text() if callable(getattr(result, "text", None)) else result.content
        return str(text)

    return caption


def tesseract_ocr(data: bytes) -> str:
    """OCR an image's bytes with tesseract. Raises :class:`OcrUnavailable` if absent.

    The ``pytesseract`` package is pure-Python and always importable, but it shells
    out to the ``tesseract`` **binary**; on a host without it (e.g. local Windows dev
    before the Docker image) we raise a precise error so the cause is visible — not a
    silent empty string that would look like "image had no text".
    """
    import pytesseract  # local import: only needed when OCR actually runs
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            return str(pytesseract.image_to_string(img)).strip()
    except UnidentifiedImageError as exc:
        raise ValueError(f"not a readable image for OCR: {exc}") from exc
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailable(
            "tesseract OCR binary not found on this host (install tesseract-ocr; "
            "it ships in the backend Docker image)"
        ) from exc


def ocr_available() -> bool:
    """Whether the tesseract binary is installed on this host (probed once).

    The worker calls this so OCR is only wired into the context when it can actually
    run — then an OCR call never raises :class:`OcrUnavailable` mid-ingestion, and a
    dev box without tesseract simply relies on the vision model (graceful degradation).
    """
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 — any failure (missing binary/import) → OCR off
        return False


def build_load_context(
    *,
    vision_model: BaseChatModel | None,
    ocr_enabled: bool,
) -> LoadContext:
    """Assemble the :class:`LoadContext` the worker injects into the loaders.

    ``vision_model`` ``None`` → no captioner (no vision model configured for the
    owner). ``ocr_enabled`` False → no OCR. With neither, image content can't be
    extracted and an image-only source will fail with a clear reason.
    """
    return LoadContext(
        caption_image=make_vision_captioner(vision_model) if vision_model is not None else None,
        ocr_image=tesseract_ocr if ocr_enabled else None,
    )
