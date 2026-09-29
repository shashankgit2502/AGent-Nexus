# ITEM 2 Slice A is complete, verified, and green.

Stopping here for your review before Slice B (per R6).

## What Slice A delivered — the production ingestion spine

The "pending forever" bug is fixed at all three root causes, end-to-end.

### Backend

- Runtime embedding layer (root-cause #3): `teams.embedding_model_id` + `agents.embedding_model_id` (migration `d4e5f6a7b8c9`, applied), resolved `agent → team → org-default` (`embedding_selection.py`); if none resolves → source goes `failed` with a precise reason, never silent.
- Collection per embedding model (`store.py`): each model gets `knowledge__<model_id>` at its own dimension — dimension-safe, enables true per-team/agent embedding.
- Async worker (root-cause #1, `worker.py`): register/upload now actually spawns ingestion (`pending → ingesting → ready+chunk_count / failed+error`), async-DB↔sync-embed bridge via `to_thread`, time-boxed, tracked in `app.state.ingest_tasks`, awaited on shutdown, startup crash-recovery sweep re-enqueues stuck rows.
- Real file upload (root-cause #2): `POST /teams/{id}/knowledge/upload` (multipart) stores bytes → real ingestion. JSON register also triggers the worker now.
- Universal loader registry (`loaders.py`): native `txt/md/code/csv/json/team_doc` today; clean `register_file_loader` seam for B/C/D; unsupported format → honest `failed`, not a hang.
- Delete + vector cleanup: `DELETE …/knowledge/{id}` soft-deletes the source and hard-deletes its chunks by `source_id` metadata (verified `PGVector.delete` is ids-only in `0.0.17` → metadata SQL on the same DB) → no stale RAG.
- `KnowledgeSourceRead` now exposes `error`.

### Frontend

(Theme untouched)

- Kind→input switch with a real drag/drop + picker file upload (any type).
- A team embedding-model picker (runtime).
- Live `status + chunk_count` polling until terminal.
- Failure-reason display.
- Per-source delete.

### Docs

- `ARCH §14` (knowledge routes) updated.
- `TECHNICAL §11.2` (embedding columns) updated.

---

## Verification

### Backend

- `ruff` + `mypy` clean on all changed files.
- Knowledge + providers suites: `38/38` pass.
- Full suite: `243 passed / 1 skipped`.

### Frontend

- `tsc` + ESLint clean.
- `77/77` vitest pass.

### New tests

- 10 loader units.
- 2 end-to-end worker tests:
  - upload → ready → delete
  - misconfig → failed-with-reason

---

## Two honest flags (R3 — not hidden)

### 1. Pre-existing intermittent flake

`test_conversation_messages_rehydrate_in_order` (chat, timing) failed once in the full run, passed on re-run and in every isolation.

It's a latent race in that chat test; my startup-recovery sweep adds background load that can surface it.

Not a knowledge-correctness regression.

Worth hardening that test's wait condition separately.

### 2. Pre-existing lint

One `E501` in:

```text
app/streaming/store_pg.py:80
```

(untouched by me)

Left as-is to avoid scope creep; flagging it.

---

# Teaching wrap-up (Intermediate)

## Key concept

The async/sync bridge:

The DB is async (`asyncpg`) but the embed+PGVector path is sync (`psycopg`).

The worker does:

1. DB work async
2. `asyncio.to_thread` for the blocking embed/store
3. Async status writes

Mixing them naively would block the event loop.

## Production detail

Durability without a broker:

The status column is the job queue; a startup sweep re-enqueues `pending/ingesting` rows, so a crash mid-ingest recovers.

That's how you get queue semantics before adding Redis/arq (the `IngestService.run` seam keeps that swap trivial).

## R1 payoff

Reading the installed `PGVector.delete` source caught that it's ids-only — guessing would've shipped a delete that silently left stale chunks.

## Check question

A user sets the team embedding model to Model A, ingests a PDF, then switches the team to Model B and searches.

Given collection-per-model:

- What does the agent retrieve and why?
- Is that correct behavior?

## Next step (Slice B)

Office formats (`pdf/docx/xlsx/pptx`) via R1-pinned loaders + the backend Dockerfile with `poppler` / `tesseract` / `libreoffice` — registered against the same loader seam, no engine changes.

# SLICE B
# Slice B is complete, verified, and green.

Stopping for review per R6.

## Slice B delivered — office formats (production-grade)

### Loaders (`app/knowledge/office_loaders.py`)

Registered against the Slice-A seam, zero worker changes:

- PDF (`pypdf`) → one doc per page, with page metadata
- DOCX (`python-docx`) → paragraphs + table cells preserved
- XLSX/XLSM (`openpyxl`, `data_only + read_only`) → one doc per row, `header: value`, sheet+row metadata
- PPTX (`python-pptx`) → one doc per slide

All read from in-memory streams (no temp files).

Scanned/image-only docs surface as:

```text
failed: "no extractable text"
```

(honest — Slice C adds OCR/vision)

Legacy `.doc` / `.xls` / `.ppt` deferred to Slice D.

---

## Dependencies

Pinned + R1-verified by import:

```text
pypdf==6.13.3
python-docx==1.2.0
openpyxl==3.1.5
python-pptx==1.0.2
```

Recorded in:

- `pyproject.toml`
- `uv.lock`

---

## Backend Dockerfile + .dockerignore

Production image with the system binaries the full pipeline needs:

```text
poppler-utils
tesseract-ocr
libreoffice
libmagic1
```

Plus:

- uv lockfile-frozen install
- non-root user

Office loaders are pure-Python and don't need them; they're there so Slices C/D run unchanged in-container.

---

## Tests

### `test_office_loaders.py`

5 tests:

- PDF extraction
- DOCX extraction
- XLSX extraction
- PPTX extraction
- Registration

All use real files generated in-test.

### End-to-end

- DOCX upload → ready through the worker

### Updated

The Slice-A "unsupported format" test:

```text
pdf → zip
```

because PDF is supported now.

---

## Verification

### Knowledge tests

```text
36 knowledge tests pass
```

Breakdown:

- 18 prior
- 10 loaders
- 5 office
- 3 worker e2e

### Quality gates

- `ruff` clean
- `mypy` clean on all changed files
- `import app.main` clean

Office loaders auto-register at startup.

### Frontend

Unchanged.

The existing:

```text
File (any type)
```

upload already accepts these formats.

No frontend work needed.

### Docs

`TECHNICAL §3.1` records:

- office dependencies
- Dockerfile/system-dependencies policy

---

## One operational flag (R3 — honest)

Your C: drive is full (`101 MB` free) and uv's cache lives there, which blocked a normal install.

I redirected uv's cache + temp to `E:`:

```text
UV_CACHE_DIR=/e/uvcache
TMPDIR=/e/uvtmp
```

to install — non-destructive, and `pyproject.toml` / `uv.lock` are updated normally.

Any future uv install in this session needs that same redirect until C: is freed.

Worth clearing C: when you can.

---

# Teaching wrap-up (Intermediate)

## Key concept

The registry seam paying off:

Slice B added four formats by calling:

```python
register_file_loader(...)
```

and importing the module for its side effect.

The worker, upload endpoint, and status lifecycle were untouched — exactly what a good extension point buys you.

New coverage, zero engine risk.

---

## Production detail

Pure-Python vs system binaries:

The office formats are pure-Python (work anywhere), but true universal parsing (OCR, legacy office, the long tail) needs OS binaries.

That's why they go in a Docker image, not `pyproject.toml`.

Knowing which layer a dependency belongs to is the call that keeps the app runnable on a bare dev box while still being "no compromise" in production.

---

## Check question

An XLSX has a sheet with `10,000` rows.

My loader emits one `Document` per row.

After the `RecursiveCharacterTextSplitter` runs:

- Roughly how many chunks/vectors result?
- What's one trade-off of per-row vs per-sheet documents for retrieval quality?

---

## Next step (Slice C)

Images (`png` / `jpg`) + embedded images inside `pdf` / `docx` / `pptx`, captioned via a `supports_vision` catalog model, with `tesseract` OCR as the scanned-document fallback.

Registered against the same seam.

# SLICE 3

# Slice C is complete, verified, and green.

Stopping for review per R6.

## Slice C delivered — image ingestion (vision + OCR)

### The LoadContext mechanism (`loaders.py`)

Loaders now receive an injected context carrying optional:

- `caption_image` (vision)
- `ocr_image` (OCR)

callables — decoupling the pure loader layer from the model-resolution layer.

All existing loaders thread it through (unused where irrelevant).

`load_file_bytes` / `load_source_documents` default to an empty context, so Slice A/B callers and tests are unaffected.

---

## Standalone images (`image_loaders.py`)

Registered against the seam:

```text
png
jpg
jpeg
webp
gif
bmp
tiff
```

→ captioned + OCR'd into searchable text.

No vision/OCR configured:

```text
EmptyDocument
```

→ failed with a clear reason (honest, never silent).

---

## Embedded images (`office_loaders.py`)

### PDF

```python
page.images
```

### DOCX

```python
part.rels
```

### PPTX

```python
Picture.image
```

Embedded images are extracted and appended as captioned/OCR'd documents.

Best-effort behavior:

- One image's caption failure is logged (not swallowed — R3).
- The image is skipped.
- The document's text remains primary.

---

## Vision + OCR services (`image_processing.py`)

### Vision

`make_vision_captioner(model)`

Emits the R1-verified LangChain v1 image content block:

```json
{
  "type": "image",
  "base64": "…",
  "mime_type": "…"
}
```

### OCR

- `tesseract_ocr`
- `ocr_available()`

OCR is only wired when the binary exists.

A dev box without Tesseract gracefully falls back to vision-only.

No mid-ingest crash.

### Model resolution

`ModelResolver.resolve_catalog_model(id)`

Resolves a bare vision catalog model (no profile).

---

## Worker wiring

The worker:

1. Resolves the org-default vision model

   ```text
   first enabled supports_vision chat model
   ```

2. Detects OCR availability

3. Builds the `LoadContext`

4. Injects it into the loaders

Reuses the real:

- `EmbeddingsResolver`
- `ModelResolver`
- `IngestionService`

(R2)

---

## Dependencies

Pinned, R1-verified:

```text
pytesseract==0.3.13
```

Plus:

```text
Pillow
```

---

## Verification

### Knowledge tests

```text
44 knowledge tests pass
```

Including:

- 8 new tests
  - 7 image units
  - 1 image-upload e2e via stubbed vision

### Full backend suite

```text
256 passed
1 skipped
0 failures
```

The chat flake did not recur.

### Quality gates

- `ruff` clean
- `mypy` clean
- `app` imports cleanly

All image formats (`png/jpg/pdf/docx`) register at startup.

### Docs

`TECHNICAL §3.1` records:

- Slice C dependencies
- vision/OCR policy

### Frontend

Unchanged.

The existing:

```text
File (any type)
```

upload already accepts images.

---

## Operational note (unchanged from Slice B)

C: is still full.

`pytesseract` was installed using the E: cache redirect:

```text
UV_CACHE_DIR=/e/uvcache
TMPDIR=/e/uvtmp
```

Any future `uv install` needs that same redirect until C: is freed.

---

# Teaching wrap-up (Intermediate)

## Key concept

Dependency injection across a layer boundary:

The loaders are pure and know nothing about models.

The worker:

- resolves the vision model
- builds a captioner callable
- injects it through `LoadContext`

This keeps the loader registry testable offline (stub the callable) while real model resolution stays where it belongs.

The image-loader tests never touch a model.

---

## Production detail

Capability probing:

`ocr_available()` checks the Tesseract binary once and only wires OCR if present.

An absent binary becomes:

```text
vision-only
```

not a per-image crash.

Probing a capability up front beats catching the same failure on every call.

---

## R1 payoff

I verified the multimodal message shape against the installed:

```text
langchain_core 1.4.7
```

(`ImageContentBlock`)

rather than guessing the older:

```text
image_url
```

form.

The captioner emits the current cross-provider standard block.

---

## Check question

A 30-page scanned PDF (no text layer) is uploaded on a host with a vision model but no Tesseract.

Walk through:

- what each page produces,
- what the final source status is,

and how that behavior would differ if Tesseract were installed.

---

## Next step (Slice D)

The unstructured long-tail backbone (the catch-all for formats B/C don't cover) + URL fetch (`HTML → text`) + the read-only DB connector (`DSN + SELECT`) — all registered against the same seam, completing "ingest anything."

---

Want me to proceed to Slice D, or review Slice C first?


# SLICE D

# Slice D is code-complete — this finishes ITEM 2.

All offline tests pass; two DB-dependent verifications are blocked by Docker Desktop being down (details below).

## Slice D delivered — "ingest anything"

### URL sources (`web_loader.py`)

`kind='url'`

→ SSRF-guarded fetch (reuses `validate_base_url`, re-validates every redirect hop so a public URL can't 302 into the internal network)

→ routes the fetched bytes back through the universal registry by content-type:

```text
HTML → bs4
linked PDF → Slice-B PDF loader
...
```

`bs4` strips:

- script
- style
- head

noise and keeps the title.

---

### Long-tail fallback (`unstructured_fallback.py` + `unstructured_runner.py`)

A file format with no native loader:

```text
→ unstructured
```

(`rtf` / `odt` / `epub` / `eml` / …)

run in an isolated subprocess.

This was driven by a real finding:

```text
unstructured auto-partition segfaults (exit 139)
```

in-process on this box — a crash that would otherwise kill the worker.

The subprocess contains:

- crashes
- OOMs
- timeouts

so one source fails, never the app.

Verified:

```text
120s hang → caught → returned []
```

Dockerfile now pre-caches NLTK data so the container doesn't hit first-use downloads.

---

### Read-only DB connector (`db_loader.py`)

`kind='db'`

→ `{dsn, query}` in a new `connector_config` JSONB column

→ a `SELECT` run with defence-in-depth:

- `SELECT` / `WITH`-only single-statement guard
- `default_transaction_read_only=on`
- psycopg `read_only` flag
- statement timeout
- row cap
- connect timeout

Rows become:

```text
column: value
```

documents.

---

### Frontend

Kind selector wired:

- URL field
- DB DSN field
- DB SELECT field

→ stored in `connector_config`

Includes client-side validation.

```text
tsc clean
ESLint clean
```

---

## Dependencies

Pinned, R1-verified:

```text
beautifulsoup4==4.15.0
unstructured==0.23.1
```

Migration:

```text
e5f6a7b8c9d0
```

(`connector_config` column)

Docs updated:

- `TECHNICAL §3.1`
- `TECHNICAL §11.5`

---

## Verification

### Backend (offline)

```text
250 passed
3 skipped
0 failures
```

New Slice D units:

```text
19
```

Breakdown:

- web_loader: 5
- db_loader guard: 5
- unstructured_fallback isolation: 5
- others: 4

Quality gates:

```text
ruff clean
mypy clean
```

Across:

```text
17 files
```

---

### Frontend

```text
77/77 pass
```

- `tsc` clean
- ESLint clean

---

## Blocked (Docker Desktop is down — I can't start it from here)

### Apply migration

```bash
alembic upgrade head
```

Migration:

```text
e5f6a7b8c9d0
```

Written, not yet applied.

### Integration tests

```text
26 integration tests
```

including:

```text
test_db_loader_integration.py
```

which proves the read-only transaction rejects writes at the DB layer.

They skip/can't run without Postgres.

Please start Docker Desktop; then run:

```bash
docker compose up -d db
uv run alembic upgrade head
uv run pytest -m integration
```

to close those out.

Everything is written and ready.

---

## Note (unchanged)

C: is still full.

New dependencies were installed via the E: cache redirect:

```text
UV_CACHE_DIR=/e/uvcache
TMPDIR=/e/uvtmp
```

---

# ITEM 2 is functionally complete across all four slices

### Slice A

Runtime-embedding spine + worker + delete

### Slice B

`pdf` / `docx` / `xlsx` / `pptx`

### Slice C

Images + embedded-image vision/OCR

### Slice D

URL + long-tail + DB

The:

```text
stuck pending · 0 chunks
```

bug is fixed at all three root causes.

The system now ingests essentially:

- any document
- URL
- read-only DB query

production-grade, with honest failure states throughout.

---

# Teaching wrap-up (Intermediate)

## Key concept

Fault isolation via process boundaries.

The segfault is the lesson.

A native crash cannot be caught with:

```python
try:
    ...
except:
    ...
```

because it kills the interpreter.

The only reliable handling strategy is:

```text
run risky code in a subprocess
→ inspect exit code
→ convert failure into data
```

That's why untrusted-input parsers (and heavy `unstructured`) belong behind a process boundary in production.

---

## Security takeaway

Defence in depth.

The DB connector does not trust the `SELECT` keyword check alone.

It also sets a read-only transaction at the database.

So even if the query guard were bypassed:

```text
the database still refuses writes
```

Layered controls beat any single check.

---

## Check question

The URL loader re-validates the host on every redirect hop.

What concrete attack does validating only the initial URL miss?

Why does routing fetched bytes by `Content-Type` (not the URL extension) matter for a link like:

```text
https://x.com/report?id=5
```

?

---

## Next step

Once Docker is up:

```bash
docker compose up -d db
uv run alembic upgrade head
uv run pytest -m integration
```

to close ITEM 2.

Then:

```text
ITEM 3
```

(RCA-first, per your standing preference).