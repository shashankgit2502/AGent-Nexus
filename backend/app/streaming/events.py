"""AG-UI event contract — envelope, catalog, and envelope builder (ARCH §24.3/§24.4).

This module is the **single source of truth seam** for the AG-UI event contract on
the backend. BUILD_PLAYBOOK's "don't skip" checks call out the AG-UI types as *the
one place backend/frontend silently drift* — so the catalog here is locked to
ARCHITECTURE.md §24.4 and the frontend mirrors exactly these types
(FRONTEND_SPEC §18). Any new event type must be added in §24.4 **first**, then here.

Two layers of an event
----------------------
* **Raw record** — what a graph node appends to ``CollabState.events`` today:
  ``{"type": ..., "data": {...}}`` (see ``app/graph/state.make_event``). Nodes do
  not know the run/session/seq/ts — those are run-scoped concerns of the stream.
* **Envelope** — the full AG-UI event sent over the wire (ARCH §24.3):
  ``{type, session_id, run_id, seq, ts, data}``. ``build_event`` promotes a raw
  record into an envelope, validating the type against the locked catalog.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, TypedDict
from uuid import UUID

from pydantic import BaseModel

# ── The locked AG-UI event catalog (ARCH §24.4 == FRONTEND_SPEC §18) ──────────
# Keep in lockstep with both. Adding/removing a type here without updating §24.4
# is a contract break (BUILD_PLAYBOOK critical "don't skip" check).
AGUI_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "run_start",
        "round_start",
        "agent_turn_start",
        "reasoning",
        "tool_call",
        "tool_result",  # also carries an artifact `attachment` (ARTIFACTS §11.1 / ARCH §24.9)
        "contribution",
        "confidence",
        "critique",
        "consensus_update",
        "hitl_request",
        "hitl_resolved",
        "synthesis",
        "run_finished",
        "error",
    }
)


class AGUIEvent(TypedDict):
    """The AG-UI event envelope sent to clients (ARCH §24.3).

    ``seq`` is a monotonic per-run sequence used for ordering and replay
    (ARCH §24.8); ``ts`` is an ISO-8601 UTC timestamp.
    """

    type: str
    session_id: str
    run_id: str
    seq: int
    ts: str
    data: dict[str, Any]


class UnknownEventType(ValueError):
    """An event type outside the locked AG-UI catalog (ARCH §24.4).

    Raised at the build seam so a typo'd or drifted type fails **loudly** rather
    than streaming a contract the frontend renderer cannot switch on (R5: validate
    at boundaries; R3: never silently swallow).
    """


def _utc_now_iso() -> str:
    """Current time as an ISO-8601 UTC string (the envelope ``ts``)."""
    return datetime.now(UTC).isoformat()


# Cycle/pathology guard for ``json_safe``: past this depth the value is summarised
# as its ``repr`` instead of recursed into. Real AG-UI payloads are shallow.
_MAX_SANITIZE_DEPTH = 24


def json_safe(value: Any, *, _depth: int = 0) -> Any:
    """Coerce arbitrary event data into JSON-serialisable primitives (R5 boundary).

    Every AG-UI envelope is (a) persisted into the ``run_events`` JSONB column and
    (b) ``json.dumps``-ed onto the Redis fan-out bus — so its ``data`` MUST be pure
    JSON. But ``tool_result`` payloads carry whatever a tool returned: LangChain
    message content, LangGraph ``Command`` objects (e.g. deepagents' ``write_todos``),
    UUIDs, datetimes... A single non-JSON value used to raise inside the emitter,
    which killed the whole live stream and forced a full non-streaming re-run of the
    agent turn (the root cause of runs stalling on "thinking" and overrunning the
    turn timeout). Coercing here — at the one choke point every event passes
    through — makes the contract structural rather than hoping producers behave.

    Unknown objects degrade to ``str(value)``: the event stays renderable and the
    stream stays alive, which is the correct trade-off for a *visibility* channel.
    """
    if _depth > _MAX_SANITIZE_DEPTH:
        return repr(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        # JSON has no NaN/Infinity; Postgres JSONB rejects them outright.
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(k): json_safe(v, _depth=_depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(v, _depth=_depth + 1) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return json_safe(value.value, _depth=_depth + 1)
    if isinstance(value, BaseModel):
        return json_safe(value.model_dump(mode="json"), _depth=_depth + 1)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def build_event(
    raw: Mapping[str, Any],
    *,
    session_id: str,
    run_id: str,
    seq: int,
    ts: str | None = None,
) -> AGUIEvent:
    """Promote a raw ``{type, data}`` node record into a full AG-UI envelope.

    Args:
        raw: a record as produced by ``app/graph/state.make_event`` — must carry a
            ``type`` in the locked catalog and an optional ``data`` mapping.
        session_id / run_id: run identity for the envelope (a run belongs to a
            Session or a Conversation — ARCH §8.5/§13).
        seq: the monotonic per-run sequence (assigned by the emitter).
        ts: optional override (defaults to now, UTC) — injectable for tests.

    Raises:
        UnknownEventType: if ``raw['type']`` is not in :data:`AGUI_EVENT_TYPES`.
    """
    etype = raw.get("type")
    if etype not in AGUI_EVENT_TYPES:
        raise UnknownEventType(
            f"{etype!r} is not a valid AG-UI event type (ARCH §24.4). "
            f"Known types: {sorted(AGUI_EVENT_TYPES)}"
        )
    data = raw.get("data") or {}
    if not isinstance(data, Mapping):
        raise UnknownEventType(f"event {etype!r} carried non-mapping data: {type(data).__name__}")

    return AGUIEvent(
        type=etype,
        session_id=session_id,
        run_id=run_id,
        seq=seq,
        ts=ts or _utc_now_iso(),
        # Sanitised at the boundary: the envelope must survive JSONB persistence and
        # Redis json.dumps regardless of what a tool put in the raw record.
        data=json_safe(dict(data)),
    )
