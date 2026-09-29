"""Long-tail ingestion fallback via ``unstructured``, subprocess-isolated (Slice D).

When the universal registry has no native loader for a file's format, the worker
falls back to ``unstructured`` — the "ingest anything" backbone that covers the long
tail (rtf, odt, epub, eml, msg, …). The partitioner runs in an **isolated
subprocess** (:mod:`app.knowledge.unstructured_runner`) so a native crash, OOM, or
hang fails only that one source, never the worker or API (R3: contained, logged).

Returns ``[]`` when the fallback can't extract text (unsupported, crashed, timed
out) — the caller then surfaces the original ``UnsupportedFileFormat`` so the source
ends ``failed`` with a precise reason, never a silent success.
"""

from __future__ import annotations

import json
import logging
import subprocess  # noqa: S404 — used with a fixed argv (no shell), trusted runner module
import sys

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Generous: unstructured imports heavy models on first use. The worker also has an
# overall per-source timeout, so this is a backstop against a wedged subprocess.
_TIMEOUT_S = 120.0


def partition_with_unstructured(path: str, filename: str) -> list[Document]:
    """Partition ``path`` via the isolated unstructured runner. Returns docs or ``[]``.

    A non-zero / signal exit (e.g. SIGSEGV → negative return code) or a timeout is
    logged and yields ``[]`` — the source then fails with the original unsupported
    -format reason instead of crashing the worker.
    """
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, sys.executable, no shell
            [sys.executable, "-m", "app.knowledge.unstructured_runner", path],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("unstructured fallback timed out (%ss) for %s", _TIMEOUT_S, filename)
        return []

    if proc.returncode != 0:
        logger.warning(
            "unstructured fallback failed for %s (exit=%s): %s",
            filename,
            proc.returncode,
            (proc.stderr or proc.stdout or "")[:300],
        )
        return []

    last_line = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    try:
        result = json.loads(last_line[0])
    except json.JSONDecodeError:
        logger.warning("unstructured fallback produced unparseable output for %s", filename)
        return []

    text = result.get("text", "") if result.get("ok") else ""
    if not text.strip():
        return []
    return [Document(page_content=text, metadata={"filename": filename, "loader": "unstructured"})]
