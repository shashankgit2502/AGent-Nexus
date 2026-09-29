"""Collaboration graph nodes (ARCHITECTURE.md §7)."""

from app.graph.nodes.agent_turn import aagent_turn_node, agent_turn_node
from app.graph.nodes.consensus import aconsensus_node, consensus_node
from app.graph.nodes.consolidation import consolidation_node
from app.graph.nodes.end import end_node
from app.graph.nodes.hitl import hitl_node
from app.graph.nodes.orchestrator import aorchestrator_node, orchestrator_node
from app.graph.nodes.synthesizer import asynthesizer_node, synthesizer_node

__all__ = [
    "aagent_turn_node",
    "aconsensus_node",
    "agent_turn_node",
    "asynthesizer_node",
    "consensus_node",
    "consolidation_node",
    "end_node",
    "hitl_node",
    "aorchestrator_node",
    "orchestrator_node",
    "synthesizer_node",
]
