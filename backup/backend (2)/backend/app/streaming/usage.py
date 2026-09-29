"""Token metering for a run (ARCHITECTURE.md §21.7).

Until now nothing in the system measured anything: a grep for ``usage_metadata`` across the
backend returned two hits, both column definitions on a table with no writers. A 12-agent ×
3-round run is ~110 model calls and was completely unobservable.

How the tokens are captured (and why it is only a few lines)
------------------------------------------------------------
One ``UsageMetadataCallbackHandler`` is attached to the **top-level graph config**. LangChain
propagates callbacks down the runnable tree through contextvars, so that single handler sees
*every* model call inside the graph — mesh turns, the structured-output repair, the planner,
the synthesizer, the acceptance verifier, the artifact producer and memory consolidation —
**without threading a config through a single call site** (verified by execution against
langchain-core 1.4.7).

That propagation is what makes this tractable, because the return values are not uniform:
``with_structured_output(...).invoke()`` returns the parsed Pydantic model and discards the
``AIMessage``, so the planner and the verifier have **no recoverable usage on their return
value at all**. Only a callback observes them.

The trap: never attach a second handler downstream
--------------------------------------------------
A child config's ``callbacks`` list *replaces* the inherited handlers rather than extending
them (verified: a per-node handler left the run-level handler empty). So a per-turn handler
would silently zero the run total. Per-agent numbers are read from the turn's own
``AIMessage``s instead — see ``app.agents.runtime.usage_from_messages``.

Tokens only, deliberately
-------------------------
``cost_usd`` is left NULL. Dollars need ``model_catalog.pricing``, which has no writers, and
providers disagree on whether cached tokens are nested inside the prompt count (OpenAI) or
reported separately (Anthropic) — so one naive formula would misprice one of them. A
fabricated number is worse than an absent one.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langchain_core.callbacks import UsageMetadataCallbackHandler
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageEvent

logger = logging.getLogger(__name__)


def new_usage_callback() -> UsageMetadataCallbackHandler:
    """A fresh per-run usage handler.

    **Per run, never shared.** The model resolver caches built chat models by
    ``(catalog_id, profile_id, require_tools)`` across runs and agents, so a handler bound at
    model-construction time would aggregate concurrent runs together and cross-attribute one
    tenant's tokens to another. Binding per call — via the run's config — is what keeps
    attribution correct.
    """
    return UsageMetadataCallbackHandler()


def summarize(usage_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the handler's per-model map into a run-level summary.

    The handler keys usage by resolved model name (e.g. ``gpt-4o-2024-08-06``), which is the
    useful breakdown for a team whose agents run different models. This adds the totals the
    header needs without losing that breakdown.

    Defensive on every field: the payload originates from provider responses, so a missing or
    non-numeric count degrades to 0 rather than raising inside a run's finalisation path.
    """
    by_model: dict[str, dict[str, int]] = {}
    total_in = total_out = 0
    for model_name, counts in (usage_metadata or {}).items():
        if not isinstance(counts, Mapping):
            continue
        prompt = _as_int(counts.get("input_tokens"))
        completion = _as_int(counts.get("output_tokens"))
        by_model[str(model_name)] = {
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": _as_int(counts.get("total_tokens")) or (prompt + completion),
        }
        total_in += prompt
        total_out += completion
    return {
        "by_model": by_model,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens": total_in + total_out,
    }


def _as_int(value: Any) -> int:
    """Coerce a provider-reported count to a non-negative int (never raises)."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def usage_events(
    summary: Mapping[str, Any], *, org_id: UUID, run_id: UUID
) -> list[UsageEvent]:
    """Build one ``usage_events`` row per model used by this run.

    ``agent_id`` is left NULL by design: the run-level handler aggregates by *model*, and
    inventing a per-agent attribution the handler never produced would be a fabricated number.
    Per-agent tokens are surfaced on the ``contribution`` event instead, derived from that
    agent's own messages.

    ``cost_usd`` is left NULL until a price table exists (§21.7).
    """
    return [
        UsageEvent(
            org_id=org_id,
            run_id=run_id,
            agent_id=None,
            model_identifier=model_name,
            prompt_tokens=counts["input_tokens"],
            completion_tokens=counts["output_tokens"],
            cost_usd=None,
        )
        for model_name, counts in (summary.get("by_model") or {}).items()
    ]


async def record_usage(
    db: AsyncSession, *, org_id: UUID, run_id: UUID, summary: Mapping[str, Any]
) -> None:
    """Persist a run's token usage. Never raises into the run's finalisation path.

    Metering is observability, not the product: a failed write must be logged and stepped
    over, never allowed to fail a run that has already produced its answer (R3 — the failure
    is surfaced, not swallowed silently).
    """
    rows = usage_events(summary, org_id=org_id, run_id=run_id)
    if not rows:
        return
    try:
        db.add_all(rows)
        await db.flush()
        logger.info(
            "run %s usage: %s tokens across %d model(s)",
            run_id,
            summary.get("total_tokens", 0),
            len(rows),
        )
    except Exception:  # noqa: BLE001 — see docstring.
        logger.exception("failed to persist usage for run %s", run_id)
