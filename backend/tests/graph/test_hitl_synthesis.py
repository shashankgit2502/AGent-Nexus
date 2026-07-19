"""Step-6 acceptance: HITL + Synthesizer + End (BUILD_PLAYBOOK Step 6 / ARCH §4.5–4.7).

"Done when: a run pauses at HITL, resumes on approve/edit/reject, and produces a
final artifact."

These tests drive the full ``build_collab_graph`` with the **stub** mesh node (no
runner) so they isolate the Step-6 surface: the ``interrupt()`` pause, the
approve/edit/reject decision contract, the synthesizer merge (fallback + injected
model), and the terminal artifact. Checkpoint/resume across a *process restart* is
already covered against Postgres in ``test_build.py``; here we use ``InMemorySaver``
to exercise the decision branches fast.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.build import build_collab_graph
from app.graph.context import MeshContext
from app.graph.nodes.hitl import normalize_hitl_decision
from app.graph.state import initial_collab_state
from app.synthesis.synthesizer import LLMSynthesizer, render_synthesis_messages
from tests.agents._fakes import ScriptedToolCallingModel


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _hitl_state(**overrides: object):
    return initial_collab_state(
        goal="design the API",
        active_agent_ids=["a", "b"],
        hitl_enabled=True,
        **overrides,  # type: ignore[arg-type]
    )


# ── pause + the hitl_request review payload ──────────────────────────────────


def test_run_pauses_at_hitl_with_a_review_payload() -> None:
    app = build_collab_graph(InMemorySaver())

    result = app.invoke(_hitl_state(), _cfg("pause"))

    assert "__interrupt__" in result  # paused, not finished
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "hitl_request"
    assert payload["allowed_decisions"] == ["approve", "edit", "reject"]
    # The candidate is the top-ranked contribution (the stub's round-1 proposal).
    assert payload["candidate"].startswith("[stub]")
    assert payload["candidate_key"] == payload["ranking"][0]


# ── resume on each decision (the acceptance gate) ─────────────────────────────


def test_resume_approve_synthesises_and_finishes() -> None:
    app = build_collab_graph(InMemorySaver())
    app.invoke(_hitl_state(), _cfg("approve"))

    out = app.invoke(Command(resume="approve"), _cfg("approve"))

    assert out["status"] == "done"
    assert out["hitl_decision"] == {"type": "approve", "source": "human"}
    # Fallback merge (no model injected) = top-ranked contribution content.
    assert out["final_output"].startswith("[stub]")
    artifact = _run_finished_artifact(out)
    assert artifact["kind"] == "synthesis"
    assert artifact["content"] == out["final_output"]


def test_resume_edit_uses_human_content_verbatim() -> None:
    app = build_collab_graph(InMemorySaver())
    app.invoke(_hitl_state(), _cfg("edit"))

    out = app.invoke(
        Command(resume={"type": "edit", "content": "HUMAN FINAL ANSWER"}), _cfg("edit")
    )

    assert out["status"] == "done"
    assert out["final_output"] == "HUMAN FINAL ANSWER"
    synth = [e for e in out["events"] if e["type"] == "synthesis"]
    assert synth[0]["data"]["source"] == "human_edit"
    assert _run_finished_artifact(out)["content"] == "HUMAN FINAL ANSWER"


def test_resume_reject_produces_a_rejected_artifact_and_no_output() -> None:
    app = build_collab_graph(InMemorySaver())
    app.invoke(_hitl_state(), _cfg("reject"))

    out = app.invoke(Command(resume={"type": "reject", "reason": "off-target"}), _cfg("reject"))

    assert out["status"] == "done"
    assert out["final_output"] is None
    synth = [e for e in out["events"] if e["type"] == "synthesis"]
    assert synth[0]["data"]["rejected"] is True
    artifact = _run_finished_artifact(out)
    assert artifact["kind"] == "rejected"
    assert artifact["content"] == "off-target"


# ── lightweight path: no human, auto-approve ─────────────────────────────────


def test_lightweight_path_auto_approves_without_interrupt() -> None:
    app = build_collab_graph(InMemorySaver())
    state = initial_collab_state(goal="g", active_agent_ids=["a", "b"], hitl_enabled=False)

    out = app.invoke(state, _cfg("light"))

    assert "__interrupt__" not in out
    assert out["status"] == "done"
    assert out["hitl_decision"] == {"type": "approve", "source": "auto"}
    resolved = [e for e in out["events"] if e["type"] == "hitl_resolved"]
    assert resolved[0]["data"] == {"decision": "approve", "source": "auto"}


# ── synthesizer node uses the injected (cheaper) model when present ───────────


def test_injected_synthesizer_merges_with_the_model() -> None:
    model = ScriptedToolCallingModel(responses=[AIMessage(content="MERGED ANSWER")])
    ctx = MeshContext(synthesizer=LLMSynthesizer(model=model))
    app = build_collab_graph(InMemorySaver())
    # hitl off → auto-approve → synthesizer runs the injected model.
    state = initial_collab_state(goal="g", active_agent_ids=["a", "b"], hitl_enabled=False)

    out = app.invoke(state, _cfg("merge"), context=ctx)

    assert out["final_output"] == "MERGED ANSWER"
    synth = [e for e in out["events"] if e["type"] == "synthesis"]
    assert synth[0]["data"]["source"] == "model"


def _run_finished_artifact(out: dict) -> dict:
    finished = [e for e in out["events"] if e["type"] == "run_finished"]
    assert len(finished) == 1
    return finished[0]["data"]["artifact"]


# ── decision normalisation (validate-at-the-seam, R5) ─────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("approve", {"type": "approve", "source": "human"}),
        ("reject", {"type": "reject", "source": "human"}),
        ({"type": "approve"}, {"type": "approve", "source": "human"}),
        ({"type": "edit", "content": "x"}, {"type": "edit", "source": "human", "content": "x"}),
        (
            {"type": "reject", "reason": "r"},
            {"type": "reject", "source": "human", "reason": "r"},
        ),
        # edit without content is meaningless → fail safe to approve
        ({"type": "edit"}, {"type": "approve", "source": "human"}),
        # unrecognised → fail safe to approve (never silently)
        ("garbage", {"type": "approve", "source": "human"}),
        ({"nope": 1}, {"type": "approve", "source": "human"}),
    ],
)
def test_normalize_hitl_decision(raw: object, expected: dict) -> None:
    assert normalize_hitl_decision(raw) == expected


# ── LLMSynthesizer unit: prompt shape + text extraction ──────────────────────


def test_render_synthesis_messages_includes_goal_and_ranked_content() -> None:
    messages = render_synthesis_messages(
        goal="pick a vector store",
        success_criteria=["scales", "cheap"],
        ranked=[{"agent_id": "a", "confidence": 0.9, "content": "use pgvector"}],
    )
    human = messages[1].content
    assert "pick a vector store" in human
    assert "use pgvector" in human
    assert "confidence=0.90" in human


def test_llm_synthesizer_returns_model_text() -> None:
    model = ScriptedToolCallingModel(responses=[AIMessage(content="final merged text")])
    synth = LLMSynthesizer(model=model)

    out = synth.synthesize(goal="g", success_criteria=[], ranked=[])

    assert out == "final merged text"
