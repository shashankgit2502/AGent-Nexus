"""Consensus scoring — the maths that picks the team's answer (ARCH §8 / §8.1)."""

from app.consensus.scoring import (
    CRITIQUE_PENALTY,
    DEFAULT_AGREEMENT_THRESHOLD,
    DEFAULT_PEER_WEIGHT,
    ConsensusResult,
    PeerSignal,
    collect_peer_signal,
    peer_delta,
    score_round,
)

__all__ = [
    "CRITIQUE_PENALTY",
    "DEFAULT_AGREEMENT_THRESHOLD",
    "DEFAULT_PEER_WEIGHT",
    "ConsensusResult",
    "PeerSignal",
    "collect_peer_signal",
    "peer_delta",
    "score_round",
]
