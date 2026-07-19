"""Seed demo teams + agents (Project Ledger & Project Atlas) — manual-test fixtures.

Runnable-script twin of the ``f6a7b8c9d0e1_seed_demo_teams_agents`` migration:
inserts two ready-to-test engagement teams and their peer agents into the
**default org**, so the app has realistic data immediately after a clean DB.

  * "Project Ledger — FY2025 Financial & Controls Review" — 6 agents (file/DB/Excel/
    PDF analysis via RAG; 3 memory-ON, 3 memory-OFF).
  * "Project Atlas — Buy-Side M&A Due Diligence" — 6 agents (mesh + consensus;
    3 memory-ON, 3 memory-OFF).
  * "Project Forge — Full-Stack Feature Build Squad" — 6 agents (a CODING team that
    debates a design then PRODUCES downloadable artifacts: code files, a README, an
    architecture .docx and a project .zip). The Tech Lead carries ``doc_chart`` and is
    therefore the post-consensus **producer** (ARTIFACTS.md §2A); the other engineers
    debate the design with code_interpreter / rag / web_search. 3 memory-ON, 3 OFF.

Model guidance (assign in the UI — see below): every agent needs a **tool-capable**
model (the §9.3 ``supports_tools`` gate; non-tool models are rejected at resolution).
The producer (Tech Lead) does the file generation, so give it the strongest coding +
tool-calling model; reviewer/support roles can use a cheaper fast model. Each agent's
``description`` ends with a *Suggested model* hint, surfaced in the Agent Builder.

Agents are seeded with ``profile_id`` / ``override_model_id`` / ``embedding_model_id``
= **NULL** (and teams with ``embedding_model_id`` NULL) by design: those FKs point at
provider/model rows that are environment-specific and may not exist yet. Assign a
tool-capable inference profile (and, for memory/RAG, an embedding model) in the UI
before launching a run — the §9.3 ``supports_tools`` gate is enforced at model
resolution, not here.

Unlike the migration, running this script **is** the opt-in — no env flag and no
effect on the Alembic chain. It is idempotent: a team/agent already present (by
name, live row) is skipped, so re-running is safe.

Usage (from backend/, with the project venv):
    uv run python scripts/seed_demo_data.py            # seed (idempotent)
    uv run python scripts/seed_demo_data.py --remove   # hard-delete the 2 seeded teams
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import bindparam, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from app.db.session import engine  # noqa: E402

engine.echo = False
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("seed_demo")

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
    {
        # ── A CODING team that exercises the Artifact subsystem (ARTIFACTS.md) ──
        # The team debates a feature design, converges, and the Tech Lead — the only
        # agent with `doc_chart`, hence the §2A post-consensus PRODUCER — emits the
        # downloadable deliverables (code files, README, architecture .docx, .zip).
        # The other engineers shape the design via their proposals/critiques.
        "name": "Project Forge — Full-Stack Feature Build Squad",
        "description": (
            "A coding squad that turns a feature request into a working, downloadable "
            "scaffold: the team debates the design, converges, and the Tech Lead "
            "(producer) emits the code files, a README, an architecture document and a "
            "project .zip — all built from the agreed design."
        ),
        "goal_title": "Design and produce a downloadable feature scaffold",
        "goal_description": (
            "Given a feature request, agree a technical design (architecture, data model, "
            "API surface, test plan), then produce the deliverables as downloadable "
            "artifacts: backend + frontend code files, a README.md, an architecture "
            "summary (.docx), and a project.zip bundling them — built from the agreed "
            "design, not re-invented."
        ),
        "success_criteria": [
            "A technical design agreed (architecture, data model, API, test plan)",
            "Backend and frontend code files produced as downloadable artifacts",
            "A README.md and an architecture summary (.docx) produced",
            "All files bundled into a single downloadable project.zip",
        ],
        "agents": [
            {
                "name": "Tech Lead / Architect",
                "description": (
                    "Owns the design and is the deliverable PRODUCER: after the team "
                    "agrees, generates the code files, README, architecture .docx and the "
                    ".zip bundle. · Suggested model: Claude Opus 4.8 (strongest code "
                    "generation + reliable tool-calling to assemble every file)."
                ),
                "instructions": (
                    "You are the tech lead and architect of a full-stack build squad. Drive "
                    "the design debate to a clear, buildable plan: architecture, data model, "
                    "API surface and test strategy. You are the team's PRODUCER — after "
                    "consensus, build the deliverables from the AGREED design: backend and "
                    "frontend code files (write_code_file), a README (write_markdown), an "
                    "architecture summary (create_docx), and bundle them with create_archive "
                    "into project.zip. Build only what was agreed; do not invent new scope. "
                    "Remember the project's stack, conventions and prior decisions across "
                    "sessions."
                ),
                "capabilities": {"rag": True, "doc_chart": True},
                "memory_enabled": True,
            },
            {
                "name": "Backend Engineer",
                "description": (
                    "Proposes the backend design and concrete code (services, persistence, "
                    "business logic). · Suggested model: Claude Sonnet 4.6 (best coding "
                    "model)."
                ),
                "instructions": (
                    "You are the backend engineer. In your contributions, propose the "
                    "backend design and concrete code: API handlers, services, data access "
                    "and error handling in the team's chosen stack. Justify trade-offs and "
                    "critique peers' designs. Use code_interpreter to sanity-check logic. "
                    "Persist the stack and key backend decisions across sessions."
                ),
                "capabilities": {"rag": True, "code_interpreter": True},
                "memory_enabled": True,
            },
            {
                "name": "Frontend Engineer",
                "description": (
                    "Proposes UI components, state and API wiring. · Suggested model: "
                    "Claude Sonnet 4.6."
                ),
                "instructions": (
                    "You are the frontend engineer. Propose the UI: components, state "
                    "management and how they call the backend API, in the team's chosen "
                    "framework. Provide concrete component code in your contributions and "
                    "critique the API contract from a frontend perspective. Treat each "
                    "request as a fresh task; do not assume prior context."
                ),
                "capabilities": {"code_interpreter": True, "web_search": True},
                "memory_enabled": False,
            },
            {
                "name": "API & Data Modeler",
                "description": (
                    "Designs the data model and API contract the others build against. · "
                    "Suggested model: Claude Sonnet 4.6."
                ),
                "instructions": (
                    "You design the data model and the API contract: schemas, endpoints, "
                    "request/response shapes and validation. Make the contract explicit so "
                    "backend and frontend agree, and flag breaking changes and migration "
                    "concerns. Persist the agreed schema and API across sessions."
                ),
                "capabilities": {"rag": True, "code_interpreter": True},
                "memory_enabled": True,
            },
            {
                "name": "QA & Test Engineer",
                "description": (
                    "Defines the test plan and cases; critiques for correctness and edge "
                    "cases. · Suggested model: Claude Haiku 4.5 (fast, cost-efficient "
                    "reviewer)."
                ),
                "instructions": (
                    "You own quality. Define the test strategy and propose concrete test "
                    "cases (unit/integration/e2e) for the agreed design, and critique peers' "
                    "proposals for correctness, edge cases and error handling. Use "
                    "code_interpreter to validate examples. Answer each query independently."
                ),
                "capabilities": {"code_interpreter": True},
                "memory_enabled": False,
            },
            {
                "name": "DevOps & Docs Engineer",
                "description": (
                    "Covers build/CI, configuration and developer docs. · Suggested model: "
                    "Claude Haiku 4.5."
                ),
                "instructions": (
                    "You handle build, CI/CD, configuration and developer documentation. "
                    "Propose the run/build setup, environment config and the README outline "
                    "the producer will fill out. Research current tooling with web_search "
                    "when useful. Do not carry state between sessions."
                ),
                "capabilities": {"web_search": True, "code_interpreter": True},
                "memory_enabled": False,
            },
        ],
    },
]

_SEED_TEAM_NAMES = [t["name"] for t in SEED_TEAMS]


async def _ensure_default_org(conn: AsyncConnection) -> str:
    """Return the default org id, creating it if absent (organizations has no RLS)."""
    org_id = await conn.scalar(
        text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
        {"slug": DEFAULT_ORG_SLUG},
    )
    if org_id is not None:
        return str(org_id)
    org_id = await conn.scalar(
        text("INSERT INTO organizations (name, slug) VALUES (:name, :slug) RETURNING id"),
        {"name": DEFAULT_ORG_NAME, "slug": DEFAULT_ORG_SLUG},
    )
    logger.info("seed_demo: created default organization id=%s", org_id)
    return str(org_id)


async def _set_rls_org(conn: AsyncConnection, org_id: str) -> None:
    """Set the per-tx RLS org so tenant-table INSERT WITH CHECK passes (§11.0)."""
    # `true` = transaction-local; engine.begin() is one tx so this holds throughout.
    await conn.execute(
        text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id}
    )


async def _seed_team(conn: AsyncConnection, org_id: str, team: dict[str, Any]) -> None:
    """Insert one team (if missing) and its agents (each if missing). Idempotent."""
    team_id = await conn.scalar(
        text(
            "SELECT id FROM teams "
            "WHERE org_id = :org AND lower(name) = lower(:name) AND deleted_at IS NULL"
        ),
        {"org": org_id, "name": team["name"]},
    )
    if team_id is not None:
        logger.info("seed_demo: team %r already present — skipping", team["name"])
        team_id = str(team_id)
    else:
        team_id = str(
            await conn.scalar(
                text(
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
            )
        )
        logger.info("seed_demo: inserted team %r id=%s", team["name"], team_id)

    for agent in team["agents"]:
        already = await conn.scalar(
            text(
                "SELECT 1 FROM agents "
                "WHERE team_id = :team AND lower(name) = lower(:name) AND deleted_at IS NULL"
            ),
            {"team": team_id, "name": agent["name"]},
        )
        if already:
            logger.info("seed_demo: agent %r already present — skipping", agent["name"])
            continue
        await conn.execute(
            text(
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


async def seed() -> int:
    async with engine.begin() as conn:
        org_id = await _ensure_default_org(conn)
        await _set_rls_org(conn, org_id)
        for team in SEED_TEAMS:
            await _seed_team(conn, org_id, team)
        logger.info("seed_demo: complete — demo teams/agents are in the default org.")
    return 0


async def remove() -> int:
    """Hard-delete the two seeded teams (agents cascade via FK)."""
    async with engine.begin() as conn:
        org_id = await conn.scalar(
            text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
            {"slug": DEFAULT_ORG_SLUG},
        )
        if org_id is None:
            logger.info("seed_demo: no default org — nothing to remove")
            return 0
        await _set_rls_org(conn, str(org_id))
        res = await conn.execute(
            text("DELETE FROM teams WHERE org_id = :org AND name IN :names").bindparams(
                bindparam("names", expanding=True)
            ),
            {"org": str(org_id), "names": _SEED_TEAM_NAMES},
        )
        logger.warning("seed_demo: removed %d seeded team(s) (agents cascaded)", res.rowcount)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Seed (or remove) the demo teams + agents.")
    p.add_argument(
        "--remove",
        action="store_true",
        help="hard-delete the two seeded teams instead of inserting them",
    )
    args = p.parse_args()

    async def _amain() -> int:
        # Run + dispose the engine in ONE event loop (the pool is loop-bound).
        try:
            return await (remove() if args.remove else seed())
        finally:
            await engine.dispose()

    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
