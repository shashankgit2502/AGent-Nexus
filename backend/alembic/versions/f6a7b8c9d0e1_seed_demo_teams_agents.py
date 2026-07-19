"""seed demo teams + agents (Project Ledger & Project Atlas) — manual-test fixtures

Inserts two ready-to-test engagement teams and their peer agents into the **default
org**, so the app has realistic data immediately after a clean DB:

  * "Project Ledger — FY2025 Financial & Controls Review" — 6 agents (file/DB/Excel/
    PDF analysis via RAG; 3 memory-ON, 3 memory-OFF).
  * "Project Atlas — Buy-Side M&A Due Diligence" — 6 agents (mesh + consensus;
    3 memory-ON, 3 memory-OFF).

Agents are seeded with ``profile_id`` / ``override_model_id`` / ``embedding_model_id``
= **NULL** (and teams with ``embedding_model_id`` NULL) by design: those FKs point at
provider/model rows that are environment-specific and may not exist yet. Assign a
tool-capable inference profile (and, for memory/RAG, an embedding model) in the UI
before launching a run — the §9.3 ``supports_tools`` gate is enforced at model
resolution, not here.

Opt-in (like the wipe migration): a plain ``alembic upgrade head`` is a **NO-OP**
unless ``ALEMBIC_SEED_DEMO_DATA=1`` is set, so this never pollutes CI/test/prod.

    # bash / git-bash
    ALEMBIC_SEED_DEMO_DATA=1 uv run alembic upgrade head

    # PowerShell
    $env:ALEMBIC_SEED_DEMO_DATA = "1"; uv run alembic upgrade head

Idempotent: a team/agent already present (by name, live row) is skipped, so re-running
is safe. ``downgrade`` hard-deletes the two seeded teams (agents cascade via FK),
regardless of the env flag.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-21
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

_TRUTHY = {"1", "true", "yes", "on"}
DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default Organization"

# ──────────────────────────────────────────────────────────────────────────────
# Seed payload. capabilities keys are the registry's single source of truth:
# rag / web_search / code_interpreter / doc_chart / image_gen (app.agents.config).
# ──────────────────────────────────────────────────────────────────────────────
SEED_TEAMS: list[dict[str, Any]] = [
    {
        "name": "Project Ledger — FY2025 Financial & Controls Review",
        "description": (
            "Audit/financial-review engagement analyzing Northwind Manufacturing's "
            "FY2025 statements, ledger and ERP transactions via uploaded knowledge."
        ),
        "goal_title": "Form a financial-statement and controls opinion",
        "goal_description": (
            "Analyze the uploaded annual report (PDF), trial balance (Excel) and ERP GL "
            "transactions (DB); reconcile across sources, surface anomalies and controls "
            "weaknesses, and recommend a clean vs qualified opinion."
        ),
        "success_criteria": [
            "Revenue/EBITDA reconciled across PDF, Excel and DB with discrepancies flagged",
            "Top transaction anomalies and controls weaknesses identified",
            "Clean vs qualified opinion recommended with the three biggest risks",
        ],
        "agents": [
            {
                "name": "Audit Engagement Lead",
                "description": "Owns the engagement; synthesizes findings into an opinion.",
                "instructions": (
                    "You lead a financial-statement and controls review. Use the "
                    "search_knowledge tool to ground every claim in the uploaded annual "
                    "report, trial balance and ERP transactions. Synthesize your peers' "
                    "findings into a clean vs qualified opinion. Remember the client, "
                    "engagement scope and agreed materiality threshold across sessions."
                ),
                "capabilities": {"rag": True, "doc_chart": True},
                "memory_enabled": True,
            },
            {
                "name": "Financial Statements Analyst",
                "description": "Ratios, trends and MD&A from the audited statements.",
                "instructions": (
                    "Analyze the annual report (PDF) via search_knowledge: compute key "
                    "ratios, margins and YoY trends, and interpret the MD&A. Show your "
                    "figures. Persist the headline numbers and assumptions so later "
                    "sessions stay consistent."
                ),
                "capabilities": {"rag": True, "code_interpreter": True, "doc_chart": True},
                "memory_enabled": True,
            },
            {
                "name": "Ledger & Transactions Analyst",
                "description": "Anomaly detection over the trial balance and GL transactions.",
                "instructions": (
                    "Examine the trial balance (Excel) and GL transactions (DB) via "
                    "search_knowledge. Flag anomalies: unusual journal entries, round-number "
                    "postings, period-end spikes, duplicate entries. Treat each query as a "
                    "fresh analysis; do not assume prior context."
                ),
                "capabilities": {"rag": True, "code_interpreter": True},
                "memory_enabled": False,
            },
            {
                "name": "Internal Controls & Fraud Reviewer",
                "description": "Controls weaknesses and fraud red flags.",
                "instructions": (
                    "Assess internal controls and fraud risk using search_knowledge over the "
                    "ingested sources. Map anomalies to specific control weaknesses and ICFR "
                    "implications. Remember previously identified weaknesses across sessions."
                ),
                "capabilities": {"rag": True, "web_search": True},
                "memory_enabled": True,
            },
            {
                "name": "Data Reconciliation Analyst",
                "description": "Cross-checks figures across PDF, Excel and DB.",
                "instructions": (
                    "Reconcile the same figures (revenue, EBITDA, cash) across the annual "
                    "report, trial balance and GL transactions via search_knowledge. Report "
                    "exact discrepancies and which source disagrees. Answer each query "
                    "independently."
                ),
                "capabilities": {"rag": True},
                "memory_enabled": False,
            },
            {
                "name": "Reporting & Disclosure Specialist",
                "description": "Drafts the findings memo and disclosures.",
                "instructions": (
                    "Draft a concise findings memo from the team's conclusions, grounded in "
                    "search_knowledge. Structure: scope, key findings, anomalies, controls, "
                    "recommendation. Do not carry state between sessions."
                ),
                "capabilities": {"rag": True, "doc_chart": True},
                "memory_enabled": False,
            },
        ],
    },
    {
        "name": "Project Atlas — Buy-Side M&A Due Diligence",
        "description": (
            "Big-Four-style advisory team performing buy-side due diligence on a "
            "mid-market acquisition for a private-equity client."
        ),
        "goal_title": "Deliver an investment recommendation on Acme Logistics",
        "goal_description": (
            "Evaluate Acme Logistics as an acquisition for Meridian Capital (ceiling "
            "$250M, conservative risk appetite): financial quality, risk/tax, commercial "
            "thesis, technology/ops, and a partner-level go/no-go."
        ),
        "success_criteria": [
            "Clear go / no-go recommendation with confidence",
            "Top financial, tax and regulatory risks identified",
            "Defensible valuation range and key value drivers",
            "Commercial and technology diligence findings summarized",
        ],
        "agents": [
            {
                "name": "Engagement Partner",
                "description": "Lead advisor; owns the client relationship and the recommendation.",
                "instructions": (
                    "You are the engagement partner on a buy-side M&A due-diligence team. "
                    "Synthesize your peers' findings into a decision-ready recommendation. "
                    "Always tie conclusions to the client's strategic intent, valuation "
                    "ceiling and risk appetite. Remember durable client and deal facts "
                    "across sessions. Be concise, balanced, and explicit about confidence."
                ),
                "capabilities": {"rag": True, "doc_chart": True},
                "memory_enabled": True,
            },
            {
                "name": "Financial Due Diligence Lead",
                "description": "Quality of earnings, working capital, valuation modeling.",
                "instructions": (
                    "You lead financial due diligence. Assess quality of earnings, normalize "
                    "EBITDA, examine working capital and debt, and build a defensible "
                    "valuation range. Show assumptions and calculations. Persist key figures "
                    "and assumptions across sessions so later analysis stays consistent."
                ),
                "capabilities": {"rag": True, "code_interpreter": True, "doc_chart": True},
                "memory_enabled": True,
            },
            {
                "name": "Risk, Tax & Compliance Advisor",
                "description": "Regulatory, tax structuring and red-flag analysis.",
                "instructions": (
                    "You advise on risk, tax and regulatory compliance for the acquisition. "
                    "Identify red flags, tax-structuring considerations and regulatory "
                    "exposure, calibrated to the client's risk appetite. Remember previously "
                    "identified risks and the client's risk profile across sessions."
                ),
                "capabilities": {"rag": True, "web_search": True},
                "memory_enabled": True,
            },
            {
                "name": "Commercial & Market Diligence Analyst",
                "description": "Market sizing, competitive landscape, growth thesis.",
                "instructions": (
                    "You perform commercial diligence: market size and growth, competitive "
                    "positioning and the demand thesis. Treat every question as a fresh "
                    "research task — do not assume prior context. Be explicit about "
                    "uncertainty."
                ),
                "capabilities": {"web_search": True, "doc_chart": True},
                "memory_enabled": False,
            },
            {
                "name": "Technology & Operations Advisor",
                "description": "IT systems, cyber, operational scalability and integration.",
                "instructions": (
                    "You assess the target's technology and operations: systems, cyber "
                    "posture, scalability and post-deal integration effort. Answer each "
                    "query independently from first principles, without relying on "
                    "remembered context."
                ),
                "capabilities": {"web_search": True, "rag": True},
                "memory_enabled": False,
            },
            {
                "name": "Sector Specialist (Logistics & Freight)",
                "description": "Industry benchmarks and sector-specific context.",
                "instructions": (
                    "You are a sector specialist in logistics and freight. Provide industry "
                    "benchmarks, sector KPIs and domain context to ground the team's "
                    "analysis. Respond to each question on its own merits; do not carry "
                    "state between sessions."
                ),
                "capabilities": {"rag": True, "web_search": True},
                "memory_enabled": False,
            },
        ],
    },
]

_SEED_TEAM_NAMES = [t["name"] for t in SEED_TEAMS]


def _seed_armed() -> bool:
    return os.getenv("ALEMBIC_SEED_DEMO_DATA", "").strip().lower() in _TRUTHY


def _ensure_default_org(bind: sa.Connection) -> str:
    """Return the default org id, creating it if absent (organizations has no RLS)."""
    org_id = bind.execute(
        sa.text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
        {"slug": DEFAULT_ORG_SLUG},
    ).scalar()
    if org_id is not None:
        return str(org_id)
    org_id = bind.execute(
        sa.text("INSERT INTO organizations (name, slug) VALUES (:name, :slug) RETURNING id"),
        {"name": DEFAULT_ORG_NAME, "slug": DEFAULT_ORG_SLUG},
    ).scalar_one()
    logger.info("seed_demo: created default organization id=%s", org_id)
    return str(org_id)


def upgrade() -> None:
    """Seed the two demo teams + agents — only when explicitly armed (see docstring)."""
    if not _seed_armed():
        logger.warning(
            "seed_demo: SKIPPED (no data inserted). Set ALEMBIC_SEED_DEMO_DATA=1 and "
            "re-run to insert the Project Ledger + Project Atlas demo teams."
        )
        return

    bind = op.get_bind()
    org_id = _ensure_default_org(bind)
    # Tenant tables use FORCE ROW LEVEL SECURITY with a policy keyed on
    # current_setting('app.current_org'); set it so the INSERT WITH CHECK passes.
    bind.execute(sa.text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id})

    for team in SEED_TEAMS:
        existing_team_id = bind.execute(
            sa.text(
                "SELECT id FROM teams "
                "WHERE org_id = :org AND lower(name) = lower(:name) AND deleted_at IS NULL"
            ),
            {"org": org_id, "name": team["name"]},
        ).scalar()
        if existing_team_id is not None:
            logger.info("seed_demo: team %r already present — skipping", team["name"])
            team_id = str(existing_team_id)
        else:
            team_id = str(
                bind.execute(
                    sa.text(
                        "INSERT INTO teams "
                        "(org_id, name, description, goal_title, goal_description, "
                        " success_criteria) "
                        "VALUES (:org, :name, :description, :goal_title, :goal_description, "
                        " CAST(:success_criteria AS jsonb)) RETURNING id"
                    ),
                    {
                        "org": org_id,
                        "name": team["name"],
                        "description": team["description"],
                        "goal_title": team["goal_title"],
                        "goal_description": team["goal_description"],
                        "success_criteria": json.dumps(team["success_criteria"]),
                    },
                ).scalar_one()
            )
            logger.info("seed_demo: inserted team %r id=%s", team["name"], team_id)

        for agent in team["agents"]:
            already = bind.execute(
                sa.text(
                    "SELECT 1 FROM agents "
                    "WHERE team_id = :team AND lower(name) = lower(:name) "
                    "AND deleted_at IS NULL"
                ),
                {"team": team_id, "name": agent["name"]},
            ).scalar()
            if already:
                logger.info("seed_demo: agent %r already present — skipping", agent["name"])
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO agents "
                    "(org_id, team_id, name, description, instructions, capabilities, "
                    " memory_enabled) "
                    "VALUES (:org, :team, :name, :description, :instructions, "
                    " CAST(:capabilities AS jsonb), :memory_enabled)"
                ),
                {
                    "org": org_id,
                    "team": team_id,
                    "name": agent["name"],
                    "description": agent["description"],
                    "instructions": agent["instructions"],
                    "capabilities": json.dumps(agent["capabilities"]),
                    "memory_enabled": agent["memory_enabled"],
                },
            )
        logger.info("seed_demo: ensured %d agents for team %r", len(team["agents"]), team["name"])

    logger.warning("seed_demo: complete — demo teams/agents are in the default org.")


def downgrade() -> None:
    """Remove the seeded teams (agents cascade via FK). Always runs (idempotent)."""
    bind = op.get_bind()
    org_id = bind.execute(
        sa.text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
        {"slug": DEFAULT_ORG_SLUG},
    ).scalar()
    if org_id is None:
        logger.info("seed_demo: no default org — nothing to remove")
        return
    bind.execute(sa.text("SELECT set_config('app.current_org', :org, true)"), {"org": str(org_id)})
    # Hard delete (not soft) so re-seeding is clean; ON DELETE CASCADE removes agents.
    result = bind.execute(
        sa.text("DELETE FROM teams WHERE org_id = :org AND name = ANY(:names)"),
        {"org": str(org_id), "names": _SEED_TEAM_NAMES},
    )
    logger.warning("seed_demo: removed %s seeded team(s) (agents cascaded)", result.rowcount)
