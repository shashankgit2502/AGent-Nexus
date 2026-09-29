"""The synthesizer node's post-consensus producer sub-step (ARTIFACTS.md §2A).

Proves the ordering + gating contract without a DB or model: the async synthesizer
node runs the injected producer **after** synthesis (so file ``tool_result`` events
stream after the ``synthesis`` event, before ``run_finished``), skips it on reject,
and the sync node never touches it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.graph.context import MeshContext
from app.graph.nodes.synthesizer import asynthesizer_node, synthesizer_node
from app.graph.state import initial_collab_state, make_event


class _FakeRuntime:
    """Minimal stand-in exposing only ``.context`` (what the node reads)."""

    def __init__(self, context: MeshContext) -> None:
        self.context = context


class _RecordingProducer:
    """Records the produce call and returns one canned artifact ``tool_result``."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def produce(
        self,
        *,
        goal: str,
        success_criteria: Sequence[str],
        final_output: str,
        ranked: Sequence[Mapping[str, Any]],
        # Part of the ``app.graph.context.Producer`` protocol: the target deliverable
        # off the orchestrator's plan (ARCH §4.1), which the synthesizer node forwards
        # so the file's kind/filename reflect what was planned. ``None`` when the run
        # had no plan. Accepted here so the stub matches the real contract.
        deliverable: Any = None,  # noqa: ANN401 — Deliverable | None, kept loose in a stub
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {"goal": goal, "final_output": final_output, "deliverable": deliverable}
        )
        return [
            make_event(
                "tool_result",
                tool="write_code_file",
                attachment={"artifact_id": "a1", "kind": "code", "filename": "main.py"},
            )
        ]


def _state(decision: dict[str, Any] | None = None) -> Any:
    state = initial_collab_state(goal="write a script", active_agent_ids=["a"], hitl_enabled=False)
    state["hitl_decision"] = decision
    return state


async def test_producer_runs_after_synthesis_and_appends_tool_result() -> None:
    producer = _RecordingProducer()
    out = await asynthesizer_node(_state(), _FakeRuntime(MeshContext(producer=producer)))

    assert len(producer.calls) == 1  # ran once, on the agreed result
    types = [e["type"] for e in out["events"]]
    assert types == ["synthesis", "tool_result"]  # files stream AFTER synthesis (§11.3)
    assert out["events"][1]["data"]["attachment"]["filename"] == "main.py"


async def test_producer_skipped_on_reject() -> None:
    producer = _RecordingProducer()
    out = await asynthesizer_node(
        _state({"type": "reject"}), _FakeRuntime(MeshContext(producer=producer))
    )

    assert producer.calls == []  # nothing agreed → nothing to build a file from
    assert out["final_output"] is None
    assert [e["type"] for e in out["events"]] == ["synthesis"]


def test_sync_node_ignores_producer() -> None:
    producer = _RecordingProducer()
    out = synthesizer_node(_state(), _FakeRuntime(MeshContext(producer=producer)))

    assert producer.calls == []  # sync path (tests) never runs the producer
    assert [e["type"] for e in out["events"]] == ["synthesis"]
