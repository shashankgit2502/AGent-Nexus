# NEX AGI backend — production image (ITEM 2: universal document ingestion).
#
# Carries the **system binaries** that pure-pip packages can't provide, so the
# "ingest anything" pipeline (ARCH §10.5) works in prod the same way for every
# format — the no-compromise path chosen for ITEM 2:
#   poppler-utils  → PDF rendering/extraction (pdf2image, unstructured PDF, Slice D)
#   tesseract-ocr  → OCR for scanned PDFs / images (Slice C)
#   libreoffice    → legacy .doc/.xls/.ppt conversion (Slice D long tail)
#   libmagic1      → true MIME detection (python-magic), not extension-trusting
#
# Slice B's office loaders (pypdf/python-docx/openpyxl/python-pptx) are pure-Python
# and need none of these; they are here so Slices C/D run unchanged in-container.
# On a dev box without these binaries the affected formats degrade to a clear
# `failed` status (never a silent hang) — see app/knowledge/loaders.py.

FROM python:3.12-slim AS runtime

# System packages for universal parsing + OCR. Cleaned in the same layer to keep
# the image lean. (libreoffice is large; drop it if legacy office is out of scope.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        libreoffice \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, reproducible, lockfile-pinned installs.
RUN pip install --no-cache-dir uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install dependencies first (cached layer) from the frozen lockfile — app code
# changes don't trigger a full reinstall.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Application code, then finalize the venv (installs the project itself).
COPY . .
RUN uv sync --frozen --no-dev

# Pre-cache the NLTK data `unstructured` uses (punkt/averaged_perceptron_tagger).
# Without this, the long-tail fallback hangs on first use downloading them at
# runtime; baking them in keeps ingestion fast and offline-safe.
RUN uv run python -c "import nltk; nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger_eng')" || true

# Run as a non-root user in production.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000

# DB migrations are applied as a separate step (alembic upgrade head) before the
# API serves traffic; the container just runs the ASGI app.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
