"""Per-agent viability partition (snapshot.partition_viable_agents) — RCA regression.

Root cause this guards (R3): ``build_mesh_context`` used to gate the whole team
all-or-nothing — the first agent whose model failed the §9.3 tool-calling gate threw,
the broad ``except`` returned ``None``, and the ENTIRE mesh ran the deterministic stub
(``[stub] …proposal for round N``) even when most agents were perfectly tool-capable.
Observed live: team ``eb006a5d`` had 4 tool-capable agents but 2 on a non-tool model
(``nvidia/nemotron-3-ultra-550b-a55b``, ``supports_tools=false``) → all 6 went stub.

The fix makes viability **per agent**: capable agents stay in the real mesh; a
non-viable agent is recorded with an actionable reason and abstains at runtime (§21.5).
These unit tests pin that contract with a fake resolver mirroring the gate — no DB, no
provider keys (the resolver is an injectable ``ModelProvider`` Protocol).
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.config import AgentConfig, Capabilities
from app.agents.snapshot import partition_viable_agents
from app.core.secrets import SecretNotFound
from app.models_layer.errors import ConnectionDisabled, ModelNotToolCapable
from app.models_layer.resolver import AgentModelRef
from tests.agents._fakes import ScriptedToolCallingModel


class _GateResolver:
    """A fake ``ModelProvider`` whose §9.3 gate verdict is keyed by ``profile_id``.

    ``tool_capable`` profiles resolve to a model; every other profile_id raises a
    resolution failure of the configured type — exactly what the real
    :class:`ModelResolver` does for a non-tool model / disabled connection / missing key.
    """

    def __init__(self, *, tool_capable: set, failure: Exception) -> None:
        self._ok = tool_capable
        self._failure = failure
        self._model: BaseChatModel = ScriptedToolCallingModel()
        self.resolved: list[AgentModelRef] = []

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> BaseChatModel:
        self.resolved.append(ref)
        if not require_tools or ref.profile_id in self._ok:
            return self._model
        raise self._failure


def _cfg(profile_id: object, *, name: str) -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name=name,
        profile_id=profile_id,  # type: ignore[arg-type]
        capabilities=Capabilities(),
    )


def test_one_non_tool_agent_does_not_collapse_the_team() -> None:
    """The RCA case: 2 tool-capable + 1 non-tool → 2 viable, 1 recorded (not all-stub)."""
    good_a = _cfg(uuid4(), name="Engagement Partner")
    good_b = _cfg(uuid4(), name="Risk Advisor")
    bad = _cfg(uuid4(), name="Financial DD Lead")  # nemotron-style non-tool model
    resolver = _GateResolver(
        tool_capable={good_a.profile_id, good_b.profile_id},
        failure=ModelNotToolCapable("nvidia/nemotron-3-ultra-550b-a55b"),
    )

    viable, nonviable = partition_viable_agents([good_a, good_b, bad], resolver)

    assert [c.id for c in viable] == [good_a.id, good_b.id]  # order preserved
    assert set(nonviable) == {str(bad.id)}
    # The recorded reason is actionable (drives the AG-UI abstention message).
    assert "does not support tool calling" in nonviable[str(bad.id)]


def test_all_non_tool_agents_yield_zero_viable() -> None:
    """Every agent non-tool → empty viable → caller selects the stub path."""
    a, b = _cfg(uuid4(), name="A"), _cfg(uuid4(), name="B")
    resolver = _GateResolver(tool_capable=set(), failure=ModelNotToolCapable("X"))

    viable, nonviable = partition_viable_agents([a, b], resolver)

    assert viable == []
    assert set(nonviable) == {str(a.id), str(b.id)}


def test_missing_secret_makes_only_that_agent_non_viable() -> None:
    """A SecretNotFound (NOT a ModelResolutionError) must still degrade per-agent."""
    good = _cfg(uuid4(), name="Capable")
    keyless = _cfg(uuid4(), name="No API key")
    resolver = _GateResolver(
        tool_capable={good.profile_id}, failure=SecretNotFound("env:MISSING_KEY")
    )

    viable, nonviable = partition_viable_agents([good, keyless], resolver)

    assert [c.id for c in viable] == [good.id]
    assert set(nonviable) == {str(keyless.id)}


def test_disabled_connection_is_recorded_per_agent() -> None:
    """A disabled connection fails just its agent, not the whole team."""
    good = _cfg(uuid4(), name="Capable")
    disabled = _cfg(uuid4(), name="Disabled conn")
    resolver = _GateResolver(
        tool_capable={good.profile_id}, failure=ConnectionDisabled("NVIDIA NIM")
    )

    viable, nonviable = partition_viable_agents([good, disabled], resolver)

    assert [c.id for c in viable] == [good.id]
    assert "is disabled" in nonviable[str(disabled.id)]
