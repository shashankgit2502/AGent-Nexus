"""Agent runtime package — config, factory, prompts, structured output (ARCH §22).

Public surface for Step 4 (Agent factory). The graph's fanned-out mesh node wires
:func:`run_agent_turn` into the parallel ``Send()`` super-step in Step 5.
"""

from app.agents.config import (
    AgentConfig,
    AgentRepository,
    Capabilities,
    InMemoryAgentRepository,
)
from app.agents.contribution import ContributionOut, CritiqueOut
from app.agents.factory import AgentBuildError, AgentFactory, ModelProvider
from app.agents.prompts import render_persona_prompt, render_round_message
from app.agents.runtime import AgentTurnError, arun_agent_turn, run_agent_turn

__all__ = [
    "AgentBuildError",
    "AgentConfig",
    "AgentFactory",
    "AgentRepository",
    "AgentTurnError",
    "Capabilities",
    "ContributionOut",
    "CritiqueOut",
    "InMemoryAgentRepository",
    "ModelProvider",
    "arun_agent_turn",
    "render_persona_prompt",
    "render_round_message",
    "run_agent_turn",
]
