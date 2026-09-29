"""Unit tests for the AG-UI envelope + locked catalog (ARCH §24.3/§24.4)."""

from __future__ import annotations

import pytest

from app.streaming.events import AGUI_EVENT_TYPES, UnknownEventType, build_event


def test_catalog_matches_architecture_24_4() -> None:
    """The catalog is locked to ARCH §24.4 / FRONTEND_SPEC §18 — guard against drift."""
    # Transcribed from the ARCH §24.4 table, in its order. A new event type is added
    # to §24.4 FIRST, then to the catalog, then here — so a diff on this set is
    # either real drift or a doc that was skipped.
    expected = {
        "run_start",
        "plan_ready",  # orchestrator's plan, once before round 1 (§4.1)
        "round_start",
        "agent_turn_start",
        "reasoning",
        "tool_call",
        "tool_result",
        "contribution",
        "confidence",
        "critique",
        "a2a_message",  # typed A2A intents (§23.3)
        "plan_amended",  # peer changed the plan mid-run (§4.1/§23.3)
        "acceptance_report",  # post-consensus acceptance check (§4.1)
        "consensus_update",
        "consensus_stalled",
        "hitl_request",
        "hitl_resolved",
        "synthesis",
        "usage",  # run token usage, once before run_finished (§21.7)
        "run_finished",
        "error",
    }
    assert AGUI_EVENT_TYPES == expected


def test_build_event_wraps_raw_record_in_full_envelope() -> None:
    event = build_event(
        {"type": "contribution", "data": {"agent_id": "a", "confidence": 0.9}},
        session_id="sess-1",
        run_id="run-1",
        seq=7,
        ts="2026-06-18T00:00:00+00:00",
    )
    assert event == {
        "type": "contribution",
        "session_id": "sess-1",
        "run_id": "run-1",
        "seq": 7,
        "ts": "2026-06-18T00:00:00+00:00",
        "data": {"agent_id": "a", "confidence": 0.9},
    }


def test_build_event_defaults_missing_data_to_empty_mapping() -> None:
    event = build_event({"type": "run_finished"}, session_id="s", run_id="r", seq=1)
    assert event["data"] == {}
    assert event["ts"]  # auto-filled ISO timestamp


def test_build_event_rejects_unknown_type() -> None:
    """Drift/typo must fail loudly at the seam (R5), not stream a bad contract."""
    with pytest.raises(UnknownEventType):
        build_event({"type": "not_a_real_event"}, session_id="s", run_id="r", seq=1)


def test_build_event_rejects_non_mapping_data() -> None:
    with pytest.raises(UnknownEventType):
        build_event({"type": "error", "data": "oops"}, session_id="s", run_id="r", seq=1)
