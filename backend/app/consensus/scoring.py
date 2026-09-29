"""Peer-weighted consensus scoring (ARCHITECTURE.md §8.1).

Pure functions: state in, numbers out. No graph, no model, no I/O — so the one piece of
maths that decides which answer the team ships can be reasoned about on its own.

The problem this fixes
----------------------
Consensus used to average **self-reported** confidence and rank by the same number. Nothing
a peer said entered the calculation: a `blocking` critique cost its target nothing, and an
agent that hallucinated and rated itself 0.95 outranked a careful agent that rated itself
0.70. That is not consensus — it is every agent grading its own homework. The workaround
had been to raise τ from 0.85 to 0.95, which does not fix the metric; it just makes
convergence unreachable so the run always burns its full round budget.

§8 always specified the missing input — *"optionally, agents cast a vote for the best peer
contribution"* — and §20 note 5 warned that raw self-confidence needs calibration before it
can be trusted in the weighted vote. Both were specified and neither was built. The A2A
channel (§23) finally provides the signal, and this module consumes it.

Adjustment, not replacement (the load-bearing design choice)
------------------------------------------------------------
Peer signal is applied as a **signed adjustment** to self-confidence::

    score = clamp(self_confidence + w_peer * peer_delta, 0, 1)     peer_delta ∈ [-1, +1]

The obvious alternative — a weighted blend ``w_self*self + w_peer*peer_score`` with
``peer_score`` normalised to ``[0,1]`` — is broken: with no peer signal every score collapses
to ``0.6 * self_confidence``, so a team whose models emit no intents, or any run resumed from
a pre-A2A checkpoint, silently has every score cut by 40% and can never reach τ. Adding a
feature would have made convergence *harder*. Here ``peer_delta = 0`` is the natural
no-signal case, so **absence of peer signal is exactly absence of change**.

Round attribution (stated, not hidden)
--------------------------------------
Messages are visible next round (§23.4), so a ``VOTE`` cast in round N is about round N-1's
work — while consensus after round N is ranking round N's contributions. The signal is
therefore attributed **to the agent** and applied to that agent's round-N contribution, the
successor of the work being judged. Scoring a contribution only with messages from the round
*after* it would leave the final round — the one the synthesizer actually consumes — with no
peer signal at all.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.a2a.messages import A2AMessage, target_of

#: What a critique costs its target, by severity. A `blocking` critique cancels exactly one
#: endorsement — the scale is deliberately symmetric so "one peer says this is broken"
#: offsets "one peer says this is good", rather than either side dominating by construction.
CRITIQUE_PENALTY: dict[str, float] = {"minor": 0.25, "major": 0.50, "blocking": 1.00}

#: How far peer signal may move a contribution's score. 0.4 means unanimous peer backing can
#: lift a self-rated 0.6 to 1.0, and unanimous rejection can drop it to 0.2 — enough for the
#: team to overrule an individual's certainty, not enough to erase a well-founded one.
#: Module constants rather than blackboard channels: these are engine tuning, not shared mesh
#: state. Promote them to `CollabState` beside `confidence_threshold` if per-team tuning is
#: ever needed.
DEFAULT_PEER_WEIGHT = 0.4

#: Absolute floor for the agreement threshold, however large the team. Below a quarter of
#: the ballots there is no leader worth calling a consensus, no matter how many candidates
#: split the rest.
AGREEMENT_FLOOR = 0.25

#: Legacy/fixed threshold, kept as the explicit override for callers that want a flat rule.
#: The *default* behaviour is :func:`required_agreement`, which scales with team size.
DEFAULT_AGREEMENT_THRESHOLD = 0.5

#: Beyond this many endorsing/critiquing peers, additional signal saturates instead of being
#: divided further. See :func:`peer_delta` for why this is not simply ``N - 1``.
PEER_SIGNAL_SATURATION = 3


def required_agreement(roster_size: int) -> float:
    """The vote share a leader must reach for a team of this size to count as agreed.

    A **fixed** majority is the wrong test at both ends of the range, which is why this
    scales. With N agents each casting one vote for a peer, votes spread over N-1 possible
    candidates, so the share a genuine leader attracts falls as the team grows:

    ==========  ==================  =====================================================
    Team size   Required share      Why
    ==========  ==================  =====================================================
    3           0.577               near-majority — with only two candidates, a leader
                                    that cannot beat 50% has not led
    5           0.447               a clear plurality; 2/5 is still a split team
    8           0.354               3/8 is a real leader among seven candidates
    12          0.289               4/12 concentrates far above the 1/11 an even
                                    scatter would produce
    ==========  ==================  =====================================================

    ``1/sqrt(N)`` decays slower than the ``1/(N-1)`` an even scatter gives, so the bar stays
    meaningfully above chance at every size while never demanding an absolute majority from
    a large team. Floored at :data:`AGREEMENT_FLOOR` so it cannot degenerate for very large
    teams.

    Keeping the flat 0.5 would have made convergence progressively **harder** as teams grow
    — an 8-agent team would essentially always exhaust ``max_rounds`` — which recreates the
    "consensus is decorative, the loop is really a round counter" failure this whole design
    exists to remove, just at a different team size.
    """
    if roster_size <= 2:
        return 0.0
    return max(AGREEMENT_FLOOR, 1.0 / math.sqrt(roster_size))


@dataclass(frozen=True)
class PeerSignal:
    """What the team said about one agent's work this round."""

    endorsements: int = 0
    votes: int = 0
    critique_penalty: float = 0.0

    @property
    def raw(self) -> float:
        """Net peer signal: support minus substantiated objection."""
        return self.endorsements + self.votes - self.critique_penalty

    @property
    def any_signal(self) -> bool:
        """True if any peer said anything at all about this agent."""
        return bool(self.endorsements or self.votes or self.critique_penalty)


@dataclass(frozen=True)
class ConsensusResult:
    """The scored round: ranking, convergence, and the evidence behind both.

    The tally and per-agent scores are carried out (not just the decision) because the human
    at the HITL gate has to be able to see *who backed whom* — a single mean hides a split
    team, and preserving disagreement rather than averaging it away is the whole point of
    adding peer signal.
    """

    ranking: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    peer_deltas: dict[str, float] = field(default_factory=dict)
    tally: dict[str, int] = field(default_factory=dict)
    mean_score: float = 0.0
    mean_confidence: float = 0.0
    agreement: float | None = None
    converged: bool = False
    has_peer_signal: bool = False


def collect_peer_signal(
    *,
    messages: Sequence[A2AMessage],
    critiques: Sequence[Mapping[str, Any]],
    current_round: int,
    run_id: str | None = None,
) -> dict[str, PeerSignal]:
    """Aggregate this round's ENDORSE / VOTE / CRITIQUE into per-agent signal.

    Reads **two** sources, because an agent can register a critique either way and both are
    real peer judgement:

    * ``messages`` — the ``CRITIQUE`` intent on the A2A channel (§23.3);
    * ``critiques`` — the long-standing ``CritiqueOut`` channel (§6).

    These are distinct records from distinct model fields, so counting both is additive, not
    double-counting. Ballot integrity (no self-vote, one vote per agent per round, target
    must be a peer whose work was seen) is already enforced upstream in
    :func:`~app.a2a.messages.normalize_messages` — this function trusts the channel and only
    aggregates, which keeps validation in exactly one place.
    """
    signal: dict[str, PeerSignal] = {}

    def bump(agent: str, **delta: Any) -> None:
        current = signal.get(agent, PeerSignal())
        signal[agent] = PeerSignal(
            endorsements=current.endorsements + int(delta.get("endorsements", 0)),
            votes=current.votes + int(delta.get("votes", 0)),
            critique_penalty=current.critique_penalty + float(delta.get("penalty", 0.0)),
        )

    for message in messages:
        if message["round"] != current_round:
            continue
        if run_id is not None and message.get("run_id") != run_id:
            continue
        target = target_of(message)
        if target is None:
            continue
        if message["intent"] == "ENDORSE":
            bump(target, endorsements=1)
        elif message["intent"] == "VOTE":
            bump(target, votes=1)
        elif message["intent"] == "CRITIQUE":
            severity = str(message["payload"].get("severity") or "minor")
            bump(target, penalty=CRITIQUE_PENALTY.get(severity, CRITIQUE_PENALTY["minor"]))

    for critique in critiques:
        if critique.get("round") != current_round:
            continue
        if run_id is not None and critique.get("run_id") != run_id:
            continue
        target = str(critique.get("target_agent") or "")
        if not target:
            continue
        severity = str(critique.get("severity") or "minor")
        bump(target, penalty=CRITIQUE_PENALTY.get(severity, CRITIQUE_PENALTY["minor"]))

    return signal


def peer_delta(signal: PeerSignal, *, peer_count: int) -> float:
    """Normalise net peer signal to ``[-1, +1]``, saturating rather than diluting.

    The denominator is ``min(peer_count, PEER_SIGNAL_SATURATION)``, **not** ``peer_count``.

    Dividing by the full peer count makes the whole feature evaporate on large teams: at 12
    agents an endorsement would be worth ``1/11`` of a delta — about 0.036 of final score —
    so peer opinion would be indistinguishable from rounding. Worse, agents cannot endorse
    everyone anyway (``A2A_MAX_MESSAGES_PER_TURN`` bounds each turn), so the theoretical
    maximum is unreachable by construction and the scale would be permanently compressed.

    Saturation matches how the evidence actually reads: *"three peers independently backed
    this"* is strong support whether the team is 4 or 12, and *"two peers called it
    blocking"* is a serious objection at any size. Below the saturation point the scale is
    still proportional, so small teams behave exactly as before (at 3 agents the denominator
    is 2 — unchanged).

    A relative (min-max) normalisation was rejected for a different reason: it manufactures
    a leader even when every agent was equally ignored, producing a confident-looking number
    derived from no information.
    """
    if peer_count <= 0:
        return 0.0
    denominator = max(1, min(peer_count, PEER_SIGNAL_SATURATION))
    return max(-1.0, min(1.0, signal.raw / denominator))


def score_round(
    contributions: Sequence[Mapping[str, Any]],
    *,
    messages: Sequence[A2AMessage] = (),
    critiques: Sequence[Mapping[str, Any]] = (),
    current_round: int,
    run_id: str | None = None,
    roster_size: int = 0,
    confidence_threshold: float = 0.85,
    peer_weight: float = DEFAULT_PEER_WEIGHT,
    agreement_threshold: float | None = None,
) -> ConsensusResult:
    """Score and rank one round's contributions (§8 selection + §8.1 peer weighting).

    Convergence requires **three** conditions, not one:

    1. ``round >= 2`` — round 1 has no peer signal by construction (peers become visible
       next round, §23.4), so a round-1 "consensus" is just simultaneous self-assurance.
       This is what makes the never-converge-on-round-1 rule principled rather than
       hardcoded.
    2. ``mean(score) >= τ`` — the locked §8 termination test, now over calibrated scores.
    3. ``agreement >= required_agreement(N)`` **and** the leader is strictly ahead of the
       runner-up — the team converged on the *same* answer rather than each being separately
       confident. The bar scales with team size because votes spread across more candidates
       as N grows; a flat majority would make large teams unable to converge at all. Pass
       ``agreement_threshold`` explicitly to override with a flat rule. Skipped when no votes
       were cast, and for teams under 3 where the metric is constant by construction.

    Backward compatibility is structural, not special-cased: no messages and no critiques
    ⇒ every ``peer_delta`` is 0 ⇒ ``score == self_confidence``, and ``agreement is None``
    ⇒ the third gate is skipped. The result is then identical to the pre-§8.1 engine.
    """
    if not contributions:
        return ConsensusResult()

    signal = collect_peer_signal(
        messages=messages, critiques=critiques, current_round=current_round, run_id=run_id
    )
    # Peers who could have signalled about any one agent: everyone else on the roster. Falls
    # back to the number of contributors when no roster was supplied.
    peer_count = max(1, (roster_size or len(contributions)) - 1)

    scores: dict[str, float] = {}
    deltas: dict[str, float] = {}
    for contribution in contributions:
        agent = str(contribution["agent_id"])
        key = f"{agent}:{contribution['round']}"
        delta = peer_delta(signal.get(agent, PeerSignal()), peer_count=peer_count)
        confidence = float(contribution.get("confidence") or 0.0)
        deltas[key] = delta
        scores[key] = max(0.0, min(1.0, confidence + peer_weight * delta))

    def rank_key(contribution: Mapping[str, Any]) -> tuple[float, int, int]:
        """Order by score, breaking ties with the team's explicit preference.

        Two contributions can tie on score (identical self-confidence, symmetric peer
        signal). Falling back to list order would then hand the top slot to whoever the
        fan-out happened to return first — and, worse, make ``agreement`` meaningless: the
        single agent the team actually voted for could be ranked *second* by accident,
        scoring the team's agreement at 0. Votes break the tie, then endorsements.
        """
        key = f"{contribution['agent_id']}:{contribution['round']}"
        peer = signal.get(str(contribution["agent_id"]), PeerSignal())
        return (-scores[key], -peer.votes, -peer.endorsements)

    ranked = sorted(contributions, key=rank_key)
    ranking = [f"{c['agent_id']}:{c['round']}" for c in ranked]

    tally = {agent: s.votes for agent, s in signal.items() if s.votes}
    total_votes = sum(tally.values())
    agreement: float | None = None
    leads_outright = False
    if total_votes:
        top_agent = str(ranked[0]["agent_id"])
        top_votes = tally.get(top_agent, 0)
        agreement = top_votes / total_votes
        # A leader must also be *unambiguous*: strictly ahead of the runner-up. Share alone
        # is not enough — on a large team two candidates can tie on share and still each
        # clear a size-scaled threshold, which is a split decision, not a consensus.
        runner_up = max((v for a, v in tally.items() if a != top_agent), default=0)
        leads_outright = top_votes > runner_up

    mean_score = sum(scores.values()) / len(scores)
    mean_confidence = sum(float(c.get("confidence") or 0.0) for c in contributions) / len(
        contributions
    )
    # The agreement gate is skipped where it carries no information:
    #
    # * **no votes cast** — gating on agreement nobody expressed would deadlock any team
    #   whose models emit no intents;
    # * **fewer than 3 agents** — the no-self-vote rule forces two agents to vote for each
    #   other, so the tally is always 1–1 and the share is always exactly 0.5. Every possible
    #   outcome is identical, so the metric is constant by construction and a two-agent team
    #   could never converge no matter how strongly it agreed.
    #
    # Otherwise the bar scales with team size (see :func:`required_agreement`) and the leader
    # must also be strictly ahead of the runner-up.
    size = roster_size or len(contributions)
    threshold = (
        agreement_threshold if agreement_threshold is not None else required_agreement(size)
    )
    converged = (
        current_round >= 2
        and mean_score >= confidence_threshold
        and (
            agreement is None
            or size < 3
            or (agreement >= threshold and leads_outright)
        )
    )

    return ConsensusResult(
        ranking=ranking,
        scores=scores,
        peer_deltas=deltas,
        tally=tally,
        mean_score=mean_score,
        mean_confidence=mean_confidence,
        agreement=agreement,
        converged=converged,
        has_peer_signal=any(s.any_signal for s in signal.values()),
    )
