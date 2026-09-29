"""The A2A message contract over the blackboard (ARCHITECTURE.md §23).

This module is the **envelope**: the typed record agents use to talk to each other, and
the validation that keeps that conversation honest and bounded. It deliberately knows
nothing about LangGraph, models, or how a message was produced — §23.4 locks the *carrier*
(the agent's structured turn output) but the **envelope is the contract**, so swapping the
carrier later (real intent tools, or a network transport, §23.6) touches nothing here.

Why this exists (the gap it closes)
-----------------------------------
Before this, the mesh could do exactly two things: propose and criticise. Agents had no way
to **ask** a peer for something, **hand work over**, or **back** a peer's answer. That is
why ``SubTask.depends_on`` — recorded by the planner — was decorative: the plan said
"Analysis builds on Research", the framing printed it as English, and no runtime channel
could ever act on it. An agent that discovered mid-run that it was blocked had no way to
say so. The seven intents below are what turn a parallel poll into a team.

The seven intents (§23.3 — all v1 scope, none optional)
-------------------------------------------------------
Each one exists because it unlocks one behaviour that is otherwise impossible. The example
is the acceptance test: if the system cannot do that, the intent is not really implemented.

* ``INFORM``   — share a finding as a structured, addressable fact, not prose buried in a
  contribution. *Research posts the 3 regulations it found, tagged so Compliance can cite
  them.*
* ``REQUEST``  — ask a peer for something you need. *Analysis: "Research — I need the FY23
  loan-loss numbers before I can model this."*
* ``PROPOSE``  — put forward one piece of the solution. *Reporting proposes the report
  skeleton for others to fill.*
* ``DELEGATE`` — hand a subtask to a peer mid-run. *Audit finds an unplanned control gap and
  hands it to Compliance.* (Advisory in v1: it re-frames the peer's next turn; it never
  spawns an agent — that stays deferred, §18.)
* ``ENDORSE``  — back a peer's work: real agreement, not self-scored confidence.
  *Compliance endorses Analysis's method.*
* ``VOTE``     — weighted vote for the best peer contribution, so the team picks a winner
  instead of averaging self-ratings.
* ``CRITIQUE`` — challenge a peer's reasoning. *Review flags a gap in the sampling method.*

``ENDORSE``/``VOTE`` are the peer signal in the consensus score and ``CRITIQUE`` is its
penalty term (§8.1); ``REQUEST``/``DELEGATE`` are what make ``depends_on`` executable.
Shipping a subset silently re-creates the "poll of clones" failure this is meant to remove.

Addressing (deliberate deviation from the §23.2 sketch)
-------------------------------------------------------
``ENDORSE``/``VOTE``/``CRITIQUE`` target a **peer agent**, not a ``target_msg_id``. The unit
consensus scores is a *contribution*, already keyed ``"agent_id:round"`` (§8) — and a model
names a peer reliably while inventing a message id it never saw is a hallucination waiting
to happen. ``in_reply_to`` remains available for genuine message-to-message threading.

Delivery semantics (§23.4) — read this before expecting a reply
----------------------------------------------------------------
Messages are **visible next round**. During round N's parallel ``Send()`` fan-out, round-N
messages are being written concurrently and cannot be read; a ``REQUEST`` sent in round N is
answered in round N+1. This is intentional: it preserves parallelism and makes intra-round
deadlock impossible. The practical consequence is honest and worth stating — a run with
``max_rounds=1`` (lightweight chat, §8.5.1) gets **no benefit** from A2A at all.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal, NotRequired, TypedDict

# ── Vocabulary ────────────────────────────────────────────────────────────────

Intent = Literal[
    "INFORM", "REQUEST", "PROPOSE", "CRITIQUE", "DELEGATE", "ENDORSE", "VOTE"
]

INTENTS: frozenset[str] = frozenset(
    {"INFORM", "REQUEST", "PROPOSE", "CRITIQUE", "DELEGATE", "ENDORSE", "VOTE"}
)

#: ``recipients`` value meaning "every peer" — the usual mesh case (§23.4).
BROADCAST = "*"

#: Mirrors ``Critique.severity`` on the blackboard. Defined here rather than imported so
#: this package stays free of graph/agent imports (the envelope is standalone by design).
Severity = Literal["minor", "major", "blocking"]

#: Intents that name a specific peer in ``payload["target_agent"]``. For these the
#: recipient list is *derived* from the target, so addressing and scoring never disagree.
_TARGETED: frozenset[str] = frozenset({"CRITIQUE", "ENDORSE", "VOTE"})

#: Intents that must name a real peer (a broadcast "please someone do this" is not a
#: hand-off — it is noise, and it is how delegation storms start).
_MUST_BE_DIRECTED: frozenset[str] = frozenset({"DELEGATE"}) | _TARGETED

#: Ballots. Exempt from the per-turn message budget because they carry no body — a VOTE is
#: a target and nothing else, ~20 tokens. Counting them against the same budget as a
#: substantive INFORM meant one vote could evict the research finding a peer was waiting
#: for, which inverts the point of the budget (it exists to stop *token* storms). Their
#: own limits are stricter anyway: one VOTE per agent per round, and dedup caps ENDORSE at
#: one per target.
_BALLOTS: frozenset[str] = frozenset({"VOTE", "ENDORSE"})

#: **Write** priority — which substantive messages survive when the budget forces a drop.
#: Ordered by what it costs the team to *lose* the message: a dropped REQUEST leaves a peer
#: blocked and a dropped DELEGATE means work never gets done, so those outrank everything;
#: losing an INFORM forces a peer to re-derive a finding; losing a CRITIQUE leaves a quality
#: problem unflagged; a PROPOSE is a suggestion others can regenerate. Lower sorts first.
_WRITE_PRIORITY: dict[str, int] = {
    "REQUEST": 0,
    "DELEGATE": 0,
    "INFORM": 1,
    "CRITIQUE": 1,
    "PROPOSE": 2,
    "VOTE": 3,
    "ENDORSE": 3,
}

#: **Read** priority — the order mail is shown to its recipient, which is a different
#: question from what survives the budget. A reader must see what *demands action from it*
#: first: an unanswered REQUEST or an accepted DELEGATE changes what this agent should do
#: this round, while an ENDORSE is pleasant but requires nothing. Sorting the inbox by write
#: priority put "Analysis voted for you" above "Analysis is blocked waiting on you".
_READ_PRIORITY: dict[str, int] = {
    "REQUEST": 0,
    "DELEGATE": 0,
    "CRITIQUE": 1,
    "INFORM": 2,
    "PROPOSE": 2,
    "ENDORSE": 3,
    "VOTE": 3,
}

#: Required payload keys per intent (§23.3). Validated at the boundary (R5) because the
#: payload crosses a trust boundary: it is whatever a language model chose to emit.
_REQUIRED_PAYLOAD: dict[str, tuple[str, ...]] = {
    "INFORM": ("content",),
    "REQUEST": ("question",),
    "PROPOSE": ("content",),
    "CRITIQUE": ("target_agent", "content"),
    "DELEGATE": ("subtask",),
    "ENDORSE": ("target_agent",),
    "VOTE": ("target_agent",),
}

_SEVERITIES: frozenset[str] = frozenset({"minor", "major", "blocking"})

#: How much of a message body participates in the duplicate key. Enough to catch a model
#: restating the same finding twice; short enough that a genuine elaboration still differs.
_DEDUP_PREFIX_CHARS = 220

_WHITESPACE = re.compile(r"\s+")


class A2AMessage(TypedDict):
    """One typed message on the blackboard (the §23.2 envelope).

    Every field carries provenance on purpose. A shared blackboard is a hub topology, and
    a hub propagates one agent's false claim to every peer in a single round; ``sender`` /
    ``round`` / ``run_id`` / ``id`` are what let a reader (and the Workspace) trace a claim
    back to who said it and when, instead of absorbing it as ambient fact.

    ``run_id`` is ``NotRequired`` only so a message written before that channel existed
    still validates; real writes always stamp it (ARCH §22.5).
    """

    id: str
    run_id: NotRequired[str | None]
    round: int
    sender: str
    recipients: list[str] | Literal["*"]
    intent: Intent
    in_reply_to: NotRequired[str | None]
    payload: dict[str, Any]
    confidence: NotRequired[float | None]
    ts: str


# ── Construction helpers ──────────────────────────────────────────────────────


def new_message_id() -> str:
    """A short, collision-free message id (used as the ``in_reply_to`` correlation key)."""
    return uuid.uuid4().hex[:12]


def _utc_now_iso() -> str:
    """Envelope timestamp as an ISO-8601 UTC string."""
    return datetime.now(UTC).isoformat()


def _clean(value: Any) -> str:
    """Coerce an untrusted payload value to a trimmed string (never raises)."""
    return "" if value is None else str(value).strip()


def _dedup_key(intent: str, recipients: list[str] | str, payload: Mapping[str, Any]) -> str:
    """Near-duplicate key: intent + audience + normalised body prefix.

    Honest scope (R3 — no overclaiming): §23.5 calls for semantic-similarity dedup, which
    needs an embedding round-trip per message. This is the deterministic, zero-cost
    approximation — it collapses verbatim and whitespace/case-variant repeats, which is the
    failure mode actually observed (a model restating its own finding). True semantic dedup
    remains open.
    """
    body = " ".join(_clean(payload.get(k)) for k in ("content", "question", "subtask"))
    normalised = _WHITESPACE.sub(" ", body).strip().lower()[:_DEDUP_PREFIX_CHARS]
    audience = recipients if isinstance(recipients, str) else ",".join(sorted(recipients))
    return f"{intent}|{audience}|{normalised}"


def _delegation_depth(in_reply_to: str | None, by_id: Mapping[str, A2AMessage]) -> int:
    """How many ``DELEGATE`` hops precede this one, walking ``in_reply_to``.

    A hand-off chain with no bound is a documented multi-agent production failure: A
    delegates to B, B to C, C back to A, and the team burns its whole round budget passing
    work around instead of doing it. The walk is defensive on two axes — a cycle cannot
    hang it (``seen``), and an id that resolves to nothing simply ends the chain.
    """
    depth = 0
    seen: set[str] = set()
    cursor = in_reply_to
    while cursor and cursor not in seen:
        seen.add(cursor)
        parent = by_id.get(cursor)
        if parent is None:
            break
        if parent["intent"] == "DELEGATE":
            depth += 1
        cursor = parent.get("in_reply_to")
    return depth


# ── Validation: proposed messages → run-ready envelopes ───────────────────────


def normalize_messages(
    proposed: Sequence[Mapping[str, Any]],
    *,
    sender: str,
    current_round: int,
    run_id: str | None,
    roster: Iterable[str],
    visible_peers: Iterable[str] = (),
    existing: Sequence[A2AMessage] = (),
    budget: int = 4,
    max_delegation_depth: int = 2,
) -> tuple[list[A2AMessage], list[str]]:
    """Validate one agent's proposed messages into run-ready envelopes (§23.5).

    The proposals cross a trust boundary — they are whatever a language model emitted — so
    every rule below **drops with a recorded reason** rather than repairing silently or
    letting bad data reach the blackboard (R3/R5). The returned warnings are surfaced, not
    swallowed: an agent whose hand-off was dropped should be able to find out why.

    Rules, in order:

    1. **Unknown intent** → dropped. Only the seven §23.3 performatives exist.
    2. **Missing required payload** → dropped (e.g. a ``REQUEST`` with no question).
    3. **Targeted intents** (CRITIQUE/ENDORSE/VOTE) resolve their recipient from
       ``payload["target_agent"]``, so addressing and §8.1 scoring read the same value.
    4. **Unknown or off-roster recipient** → dropped. A message to a non-existent agent is
       never delivered, so accepting it would be a silent no-op.
    5. **Self-addressing** → dropped. Self-endorsement and self-voting are ballot-stuffing;
       self-critique is noise. This mirrors ``_valid_responds_to``'s discipline.
    6. **Targeting an unseen peer** → dropped when ``visible_peers`` is supplied. An agent
       can only honestly endorse or critique work it was actually shown (§23.4: peers are
       visible next round), so this is what stops a vote for a contribution that does not
       exist.
    7. **One VOTE per agent per round** → first kept, the rest dropped. Consensus is
       one-agent-one-ballot; without this a chatty model out-votes a careful one.
    8. **Near-duplicates** → dropped (see :func:`_dedup_key`).
    9. **Delegation depth** → a ``DELEGATE`` beyond ``max_delegation_depth`` hops is dropped.
    10. **Per-turn budget** → at most ``budget`` messages survive, kept by §23.5 priority
        (VOTE/ENDORSE/CRITIQUE > REQUEST/DELEGATE > PROPOSE/INFORM) and then by the order
        the agent wrote them. This is the O(N²) message-storm guard: N agents × N peers ×
        R rounds is unbounded without it, and every message is tokens in someone's prompt.

    Args:
        proposed: raw message dicts from the carrier (§23.4). Carrier-agnostic on purpose.
        sender: the authoring agent. Never taken from the payload — a model must not be
            able to send mail as a peer (spoofing is an inter-agent-communication risk).
        current_round / run_id: stamped onto every envelope for provenance + run scoping.
        roster: the run's ``active_agent_ids`` — the only valid recipients.
        visible_peers: peers whose prior-round work this agent actually saw (rule 6).
        existing: messages already on the blackboard, used to resolve ``in_reply_to`` for
            the delegation-depth walk.
        budget / max_delegation_depth: the §23.5 limits.

    Returns:
        ``(messages, warnings)`` — validated envelopes and one human-readable line per drop.
    """
    known = {str(a) for a in roster}
    seen_peers = {str(p) for p in visible_peers}
    by_id: dict[str, A2AMessage] = {m["id"]: m for m in existing}
    warnings: list[str] = []
    accepted: list[A2AMessage] = []
    dedup_seen: set[str] = set()
    voted = any(
        m["sender"] == sender and m["intent"] == "VOTE" and m["round"] == current_round
        for m in existing
    )

    for index, raw in enumerate(proposed):
        label = f"message {index + 1} from {sender}"

        intent = _clean(raw.get("intent")).upper()
        if intent not in INTENTS:
            warnings.append(f"{label}: unknown intent {intent or '(empty)'!r}; dropped")
            continue

        payload = raw.get("payload")
        payload = dict(payload) if isinstance(payload, Mapping) else {}
        missing = [key for key in _REQUIRED_PAYLOAD[intent] if not _clean(payload.get(key))]
        if missing:
            warnings.append(f"{label}: {intent} is missing {', '.join(missing)}; dropped")
            continue

        recipients, reason = _resolve_recipients(
            raw,
            intent=intent,
            payload=payload,
            sender=sender,
            known=known,
            seen_peers=seen_peers,
        )
        if recipients is None:
            warnings.append(f"{label}: {intent} {reason}; dropped")
            continue

        if intent == "CRITIQUE":
            severity = _clean(payload.get("severity")).lower()
            # An out-of-vocabulary severity would silently mis-weight the §8.1 penalty
            # term, so it is normalised to the mildest value rather than trusted.
            payload["severity"] = severity if severity in _SEVERITIES else "minor"

        if intent == "VOTE":
            if voted:
                warnings.append(f"{label}: {sender} already voted this round; dropped")
                continue
            voted = True

        key = _dedup_key(intent, recipients, payload)
        if key in dedup_seen:
            warnings.append(f"{label}: near-duplicate {intent}; dropped")
            continue
        dedup_seen.add(key)

        in_reply_to = _clean(raw.get("in_reply_to")) or None
        if intent == "DELEGATE":
            depth = _delegation_depth(in_reply_to, by_id)
            if depth >= max_delegation_depth:
                warnings.append(
                    f"{label}: DELEGATE would be hop {depth + 1}, over the limit of "
                    f"{max_delegation_depth}; dropped (do the work rather than passing it on)"
                )
                continue

        message: A2AMessage = {
            "id": new_message_id(),
            "run_id": run_id,
            "round": current_round,
            # Authorship is assigned, never accepted from the payload — see Args.
            "sender": sender,
            "recipients": recipients,
            "intent": intent,  # type: ignore[typeddict-item]  # guarded by INTENTS above
            "in_reply_to": in_reply_to,
            "payload": payload,
            "confidence": _coerce_confidence(raw.get("confidence")),
            "ts": _utc_now_iso(),
        }
        accepted.append(message)

    return _apply_budget(accepted, budget=budget, sender=sender, warnings=warnings), warnings


def _resolve_recipients(
    raw: Mapping[str, Any],
    *,
    intent: str,
    payload: Mapping[str, Any],
    sender: str,
    known: set[str],
    seen_peers: set[str],
) -> tuple[list[str] | Literal["*"] | None, str]:
    """Resolve and validate a message's audience, or ``(None, reason)`` to drop it.

    Targeted intents take their recipient from ``payload["target_agent"]`` so that the
    address and the value §8.1 scores are the same string by construction. Everything else
    reads ``recipients``, defaulting to broadcast — which is the normal mesh case
    ("everyone reads the board", §23.4).
    """
    if intent in _TARGETED:
        target = _clean(payload.get("target_agent"))
        if target == sender:
            return None, "targets its own sender (no self-vote / self-endorse / self-critique)"
        if target not in known:
            return None, f"names unknown agent {target!r}"
        if seen_peers and target not in seen_peers:
            return None, (
                f"targets {target!r}, whose work this agent has not been shown "
                "(peers become visible next round, §23.4)"
            )
        return [target], ""

    value = raw.get("recipients", BROADCAST)
    if isinstance(value, str):
        if value == BROADCAST:
            if intent in _MUST_BE_DIRECTED:
                return None, "must name a specific peer, not broadcast"
            return BROADCAST, ""
        value = [value]
    if not isinstance(value, (list, tuple)):
        return None, f"has an unreadable recipients value ({type(value).__name__})"

    kept = [r for r in (_clean(v) for v in value) if r and r != sender and r in known]
    if not kept:
        return None, "names no reachable recipient"
    # Order-preserving de-duplication so one peer is never addressed twice.
    return list(dict.fromkeys(kept)), ""


def _coerce_confidence(value: Any) -> float | None:
    """Clamp an optional self-reported confidence into ``0.0–1.0``, or ``None``."""
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _apply_budget(
    messages: list[A2AMessage], *, budget: int, sender: str, warnings: list[str]
) -> list[A2AMessage]:
    """Keep at most ``budget`` **substantive** messages, highest-priority first (§23.5).

    Ballots (VOTE/ENDORSE) bypass the budget entirely — see :data:`_BALLOTS` for why. The
    cap therefore applies to the messages that actually cost tokens in a peer's next prompt.

    Stable within a priority band, so an agent's own ordering is respected among equals.
    ``budget <= 0`` disables the cap (an explicit opt-out, not an accident).
    """
    if budget <= 0:
        return messages
    ballots = [m for m in messages if m["intent"] in _BALLOTS]
    substantive = [m for m in messages if m["intent"] not in _BALLOTS]
    if len(substantive) <= budget:
        return messages

    ranked = sorted(
        enumerate(substantive),
        key=lambda pair: (_WRITE_PRIORITY.get(pair[1]["intent"], 9), pair[0]),
    )
    keep_ids = {id(m) for _, m in ranked[:budget]} | {id(m) for m in ballots}
    dropped = [m for m in substantive if id(m) not in keep_ids]
    warnings.append(
        f"{sender} proposed {len(substantive)} substantive messages over a budget of "
        f"{budget}; dropped {', '.join(m['intent'] for m in dropped)} (lowest priority first)"
    )
    # Preserve the agent's original ordering among survivors.
    return [m for m in messages if id(m) in keep_ids]


# ── Reading the board ─────────────────────────────────────────────────────────


def inbox_for(
    messages: Sequence[A2AMessage],
    *,
    agent_id: str,
    current_round: int,
    run_id: str | None = None,
) -> list[A2AMessage]:
    """Messages this agent should read before acting — its inbox (§23.4/§23.5).

    Returns the **previous** round's messages addressed to ``agent_id`` plus that round's
    broadcasts, excluding the agent's own. Previous-round is not a limitation to work
    around: during round N's parallel fan-out, round-N messages are still being written, so
    they provably cannot be read (§23.4).

    Ordered by **read** priority (:data:`_READ_PRIORITY`) — what demands action from this
    agent comes first. That is deliberately not the write priority: an unanswered REQUEST
    changes what this agent should do this round, while an ENDORSE requires nothing of it.

    The "read your inbox before acting on shared state" rule is the point of this function:
    an agent that reasons from the board while ignoring a ``REQUEST`` addressed to it is
    exactly the coordination failure the intents exist to remove.
    """
    prior = current_round - 1
    if prior < 1:
        return []
    mine = [
        m
        for m in messages
        if m["round"] == prior
        and m["sender"] != agent_id
        and (run_id is None or m.get("run_id") == run_id)
        and (m["recipients"] == BROADCAST or agent_id in m["recipients"])
    ]
    return sorted(mine, key=lambda m: _READ_PRIORITY.get(m["intent"], 9))


def messages_by_intent(
    messages: Sequence[A2AMessage],
    *,
    intent: str,
    current_round: int,
    run_id: str | None = None,
) -> list[A2AMessage]:
    """All messages of one intent for a given round, run-scoped.

    The read path §8.1 uses to pull the round's ``ENDORSE`` / ``VOTE`` / ``CRITIQUE``
    signal when scoring contributions.
    """
    return [
        m
        for m in messages
        if m["intent"] == intent
        and m["round"] == current_round
        and (run_id is None or m.get("run_id") == run_id)
    ]


def target_of(message: A2AMessage) -> str | None:
    """The peer a targeted message is about, or ``None`` for untargeted intents."""
    if message["intent"] not in _TARGETED:
        return None
    target = _clean(message["payload"].get("target_agent"))
    return target or None
