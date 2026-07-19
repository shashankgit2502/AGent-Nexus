"""Consolidation node — persist long-term memory after the run (ARCH §25.3, Item 3 M2).

A plain node placed **after the synthesizer** (the run's output already exists) and
before ``end_node``. It drives the post-run memory write the Item 3 RCA found
missing: each memory-enabled agent's contributions are distilled into a durable
record and its recall rollup refreshed (see :mod:`app.memory.consolidation`).

Same dependency-injection seam as the mesh ``runner`` and the ``synthesizer``: the
:class:`~app.graph.context.Consolidator` is read from the runtime context, so this
node stays thin and the store/model wiring lives at the composition root
(:func:`app.agents.snapshot.build_mesh_context`). With no context — the
foundation/mesh tests, or a team with no memory-enabled agents — it is a no-op.

Resilience (R3, architected — not error-swallowing): memory is a *side effect* of a
run that has already produced its answer. A consolidation failure is logged with a
traceback and the run still finishes cleanly; it never deadlocks or discards the
synthesised output. The node writes no blackboard channels (returns ``{}``) and emits
no AG-UI event, so it does not touch the §24.4 event contract.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.runtime import Runtime

from app.graph.context import MeshContext

logger = logging.getLogger(__name__)


def consolidation_node(state: Any, runtime: Runtime[MeshContext]) -> dict[str, Any]:  # noqa: ANN401
    """Consolidate memory-enabled agents' work into long-term memory; never fail the run."""
    consolidator = runtime.context.consolidator if runtime.context is not None else None
    if consolidator is None:
        return {}
    try:
        written = consolidator.consolidate_run(state)
    except Exception:  # noqa: BLE001 — the run is already complete; memory is best-effort.
        logger.exception("memory consolidation failed after run; continuing (run output stands)")
        return {}
    if written:
        logger.info("memory consolidation wrote %d record(s)", len(written))
    return {}
