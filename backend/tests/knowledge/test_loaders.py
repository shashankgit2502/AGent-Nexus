"""Unit tests for the universal document loaders (ITEM 2 Slice A, ARCH §10.5.1).

Pure + offline: the format-routing registry, native loaders (text/md/code/csv/
json), charset fallback, and the honest failure modes (unsupported format → raise,
empty content → raise) that the worker turns into ``status='failed'`` rather than a
silent hang (R3).
"""

from __future__ import annotations

import pytest

from app.knowledge.loaders import (
    EmptyDocument,
    UnsupportedFileFormat,
    UnsupportedSourceKind,
    load_file_bytes,
    load_source_documents,
    register_file_loader,
    supported_file_formats,
)


def test_text_and_markdown_load_whole_file() -> None:
    docs = load_file_bytes(b"# Title\n\nbody text", "notes.md")
    assert len(docs) == 1
    assert "body text" in docs[0].page_content
    assert docs[0].metadata["filename"] == "notes.md"


def test_code_files_route_to_text() -> None:
    docs = load_file_bytes(b"def f():\n    return 1\n", "mod.py")
    assert "def f()" in docs[0].page_content


def test_csv_becomes_one_document_per_row() -> None:
    csv_bytes = b"name,role\nAda,eng\nGrace,sci\n"
    docs = load_file_bytes(csv_bytes, "people.csv")
    assert len(docs) == 2
    assert "name: Ada" in docs[0].page_content and "role: eng" in docs[0].page_content
    assert docs[1].metadata["row"] == 1


def test_json_is_pretty_printed_with_stable_keys() -> None:
    docs = load_file_bytes(b'{"b":2,"a":1}', "data.json")
    content = docs[0].page_content
    # sort_keys → 'a' appears before 'b' regardless of input order.
    assert content.index('"a"') < content.index('"b"')


def test_non_utf8_bytes_fall_back_not_crash() -> None:
    # 0xff is invalid UTF-8; latin-1 fallback maps it rather than raising.
    docs = load_file_bytes(b"caf\xe9", "weird.txt")
    assert docs[0].page_content  # decoded, not crashed


def test_unsupported_format_raises() -> None:
    # A format with no registered loader → honest failure, not a guess. (.pdf/.docx/
    # etc. are registered by Slice B; a .zip archive is not.)
    with pytest.raises(UnsupportedFileFormat) as exc:
        load_file_bytes(b"PK\x03\x04 ...", "archive.zip")
    assert exc.value.fmt == "zip"


def test_empty_file_raises_empty_document() -> None:
    with pytest.raises(EmptyDocument):
        load_file_bytes(b"   \n  ", "blank.txt")


def test_team_doc_uses_inline_text() -> None:
    docs = load_source_documents("team_doc", text="shared note")
    assert docs[0].page_content == "shared note"


def test_url_kind_requires_a_uri() -> None:
    # url is handled in Slice D (fetched + routed); it just needs a uri to fetch.
    with pytest.raises(ValueError, match="url"):
        load_source_documents("url", uri=None)


def test_db_kind_is_not_a_registry_loader() -> None:
    # db is loaded by the worker's read-only connector (live DSN + SELECT), not the
    # pure loader registry — so load_source_documents rejects it.
    with pytest.raises(UnsupportedSourceKind):
        load_source_documents("db", uri="postgresql://x")


def test_register_file_loader_extends_the_registry() -> None:
    # A later slice (e.g. pdf in Slice B) registers against the same map.
    sentinel = "xyzzy"
    assert sentinel not in supported_file_formats()
    register_file_loader(sentinel, lambda data, name: load_file_bytes(b"ok", "x.txt"))
    assert sentinel in supported_file_formats()
