"""Render an agent's inbox into its round prompt (ARCHITECTURE.md §23.5).

This is the read side of the A2A channel: the point where a peer's `REQUEST` actually
reaches the agent that can answer it. It is kept out of ``app/agents/prompts.py`` because
it is protocol presentation, not persona prompting — the same rendering serves any future
carrier or surface.

Two rules shape everything here
-------------------------------
**1. Budget, don't truncate uniformly.** The intents differ enormously in size: a `VOTE`
carries no body at all, while an `INFORM` exists precisely to carry substance ("the three
regulations I found, so Compliance can cite them"). A flat per-message cap spends the same
allowance on both — starving the message that matters to pad the one that doesn't. So the
inbox has a **total character budget**, filled in §23.5 priority order, with a per-message
ceiling only to stop one verbose peer consuming everything.

**2. Unread is visible, never silent.** What does not fit is still listed, as a header with
`[not shown — inbox full]`. Dropping a peer's ask invisibly is how a team silently stops
being a team: the sender believes it asked, the recipient never knew, and neither can tell.
A clearly-marked unread message is recoverable; a vanished one is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.a2a.limits import DEFAULT_LIMITS, A2ALimits
from app.a2a.messages import BROADCAST, A2AMessage

#: One-line human framing per intent, so the receiving model knows what is being asked of
#: it without having to infer the performative from the prose.
_INTENT_VERB: dict[str, str] = {
    "INFORM": "shared a finding",
    "REQUEST": "ASKED YOU FOR SOMETHING",
    "PROPOSE": "proposed",
    "DELEGATE": "HANDED YOU WORK",
    "ENDORSE": "endorsed",
    "VOTE": "voted for",
    "CRITIQUE": "challenged",
}

#: Payload keys that carry the readable body, in the order they should be shown.
_BODY_KEYS = ("question", "subtask", "content", "reason")


def _label(agent_id: str, names: Mapping[str, str]) -> str:
    """Human name for an agent id, never a raw UUID wall (mirrors ``framing._agent_label``)."""
    name = names.get(agent_id)
    if name:
        return name
    return agent_id if len(agent_id) <= 8 else f"{agent_id[:8]}…"


def _audience(message: A2AMessage, self_id: str, names: Mapping[str, str]) -> str:
    """Whether this landed in the agent's inbox directly or by broadcast."""
    recipients = message["recipients"]
    if recipients == BROADCAST:
        return "to everyone"
    others = [_label(r, names) for r in recipients if r != self_id]
    return "to you" + (f" and {', '.join(others)}" if others else "")


def _body(message: A2AMessage, *, max_chars: int) -> str:
    """The readable body of a message, capped with an explicit marker.

    The cap is a ceiling, not the budget — see the module docstring. Truncation stays
    *visible* so the model can tell a message was shortened rather than silently reading a
    sentence that stops mid-thought.
    """
    payload = message["payload"]
    parts = [str(payload[k]).strip() for k in _BODY_KEYS if str(payload.get(k) or "").strip()]
    text = " — ".join(parts)
    if message["intent"] == "CRITIQUE":
        severity = str(payload.get("severity") or "minor")
        text = f"[{severity}] {text}"
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rstrip() + " […truncated]"
    sources = payload.get("source_urls")
    if isinstance(sources, (list, tuple)) and sources:
        # Carried through verbatim: an INFORM's whole value is that a peer can *cite* it
        # rather than re-derive it, which is impossible if the sources are dropped here.
        text += "\n    sources: " + ", ".join(str(s) for s in sources[:5])
    return text


def render_inbox(
    inbox: Sequence[A2AMessage],
    *,
    self_id: str,
    names: Mapping[str, str] | None = None,
    limits: A2ALimits = DEFAULT_LIMITS,
) -> str:
    """Render the agent's inbox as a prompt section, or ``""`` when there is no mail.

    ``inbox`` must already be the agent's own, priority-ordered mail — that is
    :func:`~app.a2a.messages.inbox_for`'s job. This function only decides how much of it
    fits and how it reads.

    Returns an empty string for an empty inbox so the caller can concatenate
    unconditionally without emitting a "you have no messages" section that costs tokens and
    says nothing.
    """
    if not inbox:
        return ""

    names = names or {}
    capped = list(inbox[: limits.inbox_max_messages]) if limits.inbox_max_messages > 0 else list(inbox)
    overflow_by_count = len(inbox) - len(capped)

    lines: list[str] = []
    unread: list[A2AMessage] = []
    spent = 0
    for message in capped:
        body = _body(message, max_chars=limits.message_max_chars)
        # Budget check happens *before* appending, so the section can never exceed the
        # budget by one long message.
        if limits.inbox_max_chars > 0 and spent + len(body) > limits.inbox_max_chars and lines:
            unread.append(message)
            continue
        spent += len(body)
        verb = _INTENT_VERB.get(message["intent"], "sent")
        sender = _label(message["sender"], names)
        header = (
            f"  - [{message['intent']}] {sender} {verb} "
            f"({_audience(message, self_id, names)}, msg {message['id']})"
        )
        # A ballot has no body by design (a VOTE is a target, not a statement), so it
        # renders as one line. Emitting "…:\n    " with nothing after it wastes a line and
        # reads as a message whose content failed to load.
        lines.append(header if not body else f"{header}:\n    {body}")

    for message in unread:
        sender = _label(message["sender"], names)
        lines.append(
            f"  - [{message['intent']}] {sender} (msg {message['id']}) "
            "— [not shown — inbox full]"
        )
    if overflow_by_count > 0:
        lines.append(f"  - … and {overflow_by_count} more message(s) not shown")

    return (
        "\nYOUR INBOX (messages your peers addressed to you last round — read these "
        "BEFORE writing your contribution):\n"
        + "\n".join(lines)
        + "\nAnswer any REQUEST aimed at you, and take on any DELEGATE aimed at you, in "
        "this round's contribution. Reply to a specific message with `in_reply_to` set to "
        "its msg id."
    )
