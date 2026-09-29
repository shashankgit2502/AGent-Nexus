"""Config-time §9.3 enforcement: a peer agent's assigned model must be tool-capable.

ARCH §9.3 makes ``supports_tools`` a **hard gate** for mesh agents. At *runtime* a
non-tool agent abstains per-turn (§21.5, ``snapshot.partition_viable_agents``); this
module pushes the *same* gate forward to **config time** so the Agent Builder rejects
assigning a non-tool model the moment it is saved — instead of letting the
misconfiguration sit until a run silently degrades that agent to an abstention.

This does not reopen the locked decision; it enforces it earlier. ``supports_tools`` is
a static catalog fact (seeded from models.dev or set manually), independent of the
connection's validation probe, so gating on it never blocks configuring an agent before
its provider key is validated (the prior reason the gate was deferred).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InferenceProfile, ModelCatalog
from app.db.repositories import OrgScopedRepository


class AgentModelNotToolCapable(ValueError):
    """The agent's effective model fails the §9.3 tool-calling gate (config time)."""

    def __init__(self, model_display_name: str) -> None:
        super().__init__(
            f"Model {model_display_name!r} does not support tool calling; peer agents "
            "must use a tool-capable model (ARCH §9.3). Choose a tool-capable model, or — "
            "if this model does support function calling — mark it supports_tools=true in "
            "the catalog."
        )
        self.model_display_name = model_display_name


async def assert_agent_model_tool_capable(
    session: AsyncSession,
    *,
    org_id: UUID,
    profile_id: UUID | None,
    override_model_id: UUID | None,
) -> None:
    """Raise :class:`AgentModelNotToolCapable` if the agent's effective model can't call tools.

    Effective model = the override (ARCH Q1) else the profile's default model. When no
    model is resolvable (no profile/override, or a profile with no default model) there is
    nothing to gate, so this is a no-op — the "agent has no model at all" concern is a
    separate path (the run's stub fallback / a missing-profile check). A referenced id we
    cannot read is left to the existing FK / not-found handling; we only gate a model we
    can actually load and find non-tool-capable.
    """
    model_id = override_model_id
    if model_id is None and profile_id is not None:
        profile = await OrgScopedRepository(session, InferenceProfile, org_id).get(profile_id)
        model_id = profile.default_model_id if profile is not None else None
    if model_id is None:
        return
    model = await OrgScopedRepository(session, ModelCatalog, org_id).get(model_id)
    if model is None:
        return
    if not model.supports_tools:
        raise AgentModelNotToolCapable(model.display_name)
