"""Alembic autogenerate table filter (TECHNICAL §11.8).

Extracted from ``alembic/env.py`` so the exclusion is **unit-testable** (the env
module runs migrations on import, so its internals can't be imported directly).

Why this exists (regression target, R3): autogenerate compares ``Base.metadata``
to the live DB, which also contains the LangGraph-managed tables (the bare ``store``
and ``checkpoints``/``checkpoint_*`` tables, and ``langchain_*`` PGVector tables).
Without this filter Alembic emits ``DROP TABLE`` for them. An earlier filter used the
prefix ``"store_"`` and so **missed the bare ``store`` table** — the regression this
module's tests lock down.
"""

from __future__ import annotations

# Name prefixes owned by frameworks, never by our ORM (TECHNICAL §11.8):
#   checkpoint*  → LangGraph PostgresSaver (checkpoints, checkpoint_blobs, ...)
#   store*       → LangGraph PostgresStore (the bare `store` table AND store_migrations)
#   langchain_*  → langchain-postgres / PGVector (langchain_pg_collection/embedding)
EXCLUDED_PREFIXES: tuple[str, ...] = ("checkpoint", "store", "langchain_")


def is_framework_table(name: str) -> bool:
    """True if ``name`` is a framework-managed table Alembic must not touch."""
    return any(name.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def include_object(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Alembic ``include_object`` hook: drop framework tables from autogenerate."""
    if type_ == "table" and name and is_framework_table(name):
        return False
    return True
