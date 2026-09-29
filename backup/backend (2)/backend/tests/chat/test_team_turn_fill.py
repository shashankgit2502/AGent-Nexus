"""Regression: a team chat turn's assistant message is filled from the SYNTHESIS
prose artifact, never a producer file deliverable (ARTIFACTS §2A).

Root cause (R3): the chat bubble is poll-driven — a team assistant turn stays
"pending" while ``content`` is NULL and only flips to "done" once the background run
writes the synthesized answer back to the message (``_fill_assistant`` →
``_synthesized_content``). That lookup used an **unscoped** ``scalar(select(Artifact)
.where(run_id=...))``. Once the post-consensus artifact producer began writing file
deliverables into the *same* ``artifacts`` table — many with ``content`` NULL (binary
bytes live in object storage, §7) — the query could return a file row instead of the
prose row, writing a NULL chat answer that left the turn stuck on "Thinking…" forever
even though the run had finished and streamed ``run_finished``.

Fix: scope ``_synthesized_content`` to the prose artifact (``kind in
{synthesis, rejected}``). This seeds the exact poisoning shape — a producer file
artifact created *first* (content NULL) plus the synthesis prose — and asserts the
fill resolves to the prose answer. Live-DB integration (the project's testing
preference); requires the migrated DB; marked ``integration``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.chat.service import _synthesized_content
from app.core.identity import OrgContext, seed_default_organization
from app.db.models import Artifact, Conversation, Run, Team
from app.db.session import AsyncSessionLocal, engine

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test() -> AsyncGenerator[None, None]:
    """Release pooled asyncpg connections on the test's own loop (see test_run_recovery)."""
    yield
    await engine.dispose()


async def _seed_run_with_artifacts(*, with_producer_file: bool) -> tuple[OrgContext, Run]:
    """Seed org→team→conversation→run, then a producer file (NULL content) + synthesis.

    The producer file artifact is committed **first** (mirroring §2A's mid-run commit,
    so it has the earlier ``created_at``) — the precise ordering that made the old
    unscoped ``scalar`` return the wrong row.
    """
    async with AsyncSessionLocal() as db:
        org_id = await seed_default_organization(db)
        await db.commit()
        # RLS GUC, as the background executor sets it for its own session.
        await db.execute(
            text("SELECT set_config('app.current_org', :org, false)"), {"org": str(org_id)}
        )
        org = OrgContext(org_id=org_id)

        team = Team(org_id=org_id, name=f"Fill Team {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        conversation = Conversation(
            org_id=org_id, team_id=team.id, thread_id=f"conv-{uuid4().hex}"
        )
        db.add(conversation)
        await db.flush()
        run = Run(
            org_id=org_id,
            conversation_id=conversation.id,
            query="make me a script",
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(run)
        await db.flush()

        if with_producer_file:
            # A binary producer deliverable: bytes in object storage, content NULL (§7).
            db.add(
                Artifact(
                    org_id=org_id,
                    run_id=run.id,
                    kind="code",
                    filename="script.py",
                    mime_type="text/x-python",
                    content=None,
                    storage_ref="obj/whatever",
                    size_bytes=42,
                    producer_agent_id=None,
                )
            )
            await db.commit()  # committed first → earlier created_at (the poisoning case)

        # The synthesis prose artifact `_finalize_run` writes (the chat's real answer).
        db.add(
            Artifact(
                org_id=org_id,
                run_id=run.id,
                kind="synthesis",
                content="The agreed answer.",
                content_format="markdown",
            )
        )
        await db.commit()
        return org, run


async def test_fill_prefers_synthesis_over_producer_file_artifact() -> None:
    """The poisoning case: a NULL-content file row must not become the chat answer."""
    org, run = await _seed_run_with_artifacts(with_producer_file=True)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("SELECT set_config('app.current_org', :org, false)"),
            {"org": str(org.org_id)},
        )
        content = await _synthesized_content(db, org=org, run_id=run.id)
    assert content == "The agreed answer."


async def test_fill_returns_synthesis_when_no_producer_file() -> None:
    """The prose-only case still resolves (no behavioural regression)."""
    org, run = await _seed_run_with_artifacts(with_producer_file=False)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("SELECT set_config('app.current_org', :org, false)"),
            {"org": str(org.org_id)},
        )
        content = await _synthesized_content(db, org=org, run_id=run.id)
    assert content == "The agreed answer."
