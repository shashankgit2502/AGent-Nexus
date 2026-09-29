"""A2A — the typed inter-agent message contract over the blackboard (ARCH §23).

The public surface of the package. Import from here, not from the submodule, so the
carrier decision (§23.4) and the envelope stay separable.
"""

from app.a2a.messages import (
    BROADCAST,
    INTENTS,
    A2AMessage,
    Intent,
    Severity,
    inbox_for,
    messages_by_intent,
    new_message_id,
    normalize_messages,
    target_of,
)

__all__ = [
    "BROADCAST",
    "INTENTS",
    "A2AMessage",
    "Intent",
    "Severity",
    "inbox_for",
    "messages_by_intent",
    "new_message_id",
    "normalize_messages",
    "target_of",
]
