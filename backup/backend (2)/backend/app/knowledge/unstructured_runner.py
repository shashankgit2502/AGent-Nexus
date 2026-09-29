"""Subprocess entry point: partition a file with ``unstructured`` (ITEM 2 Slice D).

Run as ``python -m app.knowledge.unstructured_runner <path>``. Reads one file, runs
``unstructured``'s auto partitioner (the long-tail "ingest anything" backbone — rtf,
odt, epub, eml, …), and writes ``{"ok": true, "text": ...}`` as JSON on the last
stdout line.

**Why a subprocess:** ``unstructured`` shells out to native libraries that can
**segfault / OOM** on adversarial input (verified: a crafted ``.rtf`` SIGSEGVs the
interpreter). Running it isolated means such a crash fails *one* knowledge source
(the parent sees a non-zero / signal exit) instead of taking down the ingestion
worker and the API. The parent (:mod:`app.knowledge.unstructured_fallback`) enforces
the timeout and interprets the exit.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: unstructured_runner <path>"}))
        return 2
    path = argv[1]
    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=path)
        text = "\n\n".join(str(e) for e in elements if str(e).strip())
        print(json.dumps({"ok": True, "text": text}))
        return 0
    except Exception as exc:  # noqa: BLE001 — reported to the parent as structured JSON
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
