"""The §23.5 anti-chaos limits, as one injectable value (ARCHITECTURE.md §23.5).

Why a dataclass instead of another blackboard channel
-----------------------------------------------------
``peer_content_max_chars`` set the precedent of carrying a render-tuning knob on
``CollabState`` to avoid threading a setting through the call chain. That is right for
*one* scalar; it does not scale to five, and every channel added to the blackboard is a
channel the Postgres checkpointer serialises on every super-step.

So these travel the dependency path instead — ``build_mesh_context`` (which already holds
``Settings``) → ``FactoryMeshRunner`` → the turn → the prompt. Every parameter has a default
matching ``config.py``, so any caller that does not supply limits still gets the shipped
behaviour rather than an unbounded channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class A2ALimits:
    """Bounds on how much agents may say to each other, and how much is read back.

    Two distinct jobs, deliberately in one value because they trade against each other:

    * **Write side** (``max_messages_per_turn``, ``max_delegation_depth``) — how much one
      agent may emit in one turn, enforced by :func:`~app.a2a.messages.normalize_messages`.
    * **Read side** (``inbox_max_chars``, ``message_max_chars``, ``inbox_max_messages``) —
      how much of the resulting mail is rendered into a peer's next prompt, enforced by
      :func:`~app.a2a.render.render_inbox`.

    Raising the write budget without raising the read budget just means more messages get
    marked unread; the pair is the real setting.
    """

    max_messages_per_turn: int = 4
    max_delegation_depth: int = 2
    inbox_max_chars: int = 4000
    message_max_chars: int = 1500
    inbox_max_messages: int = 12

    @classmethod
    def from_settings(cls, settings: Any) -> A2ALimits:
        """Build the limits from app ``Settings`` (the production path).

        Reads defensively via ``getattr`` so a settings object that predates these fields
        (or a test double) yields the dataclass defaults instead of raising.
        """
        return cls(
            max_messages_per_turn=int(
                getattr(settings, "A2A_MAX_MESSAGES_PER_TURN", cls.max_messages_per_turn)
            ),
            max_delegation_depth=int(
                getattr(settings, "A2A_MAX_DELEGATION_DEPTH", cls.max_delegation_depth)
            ),
            inbox_max_chars=int(getattr(settings, "A2A_INBOX_MAX_CHARS", cls.inbox_max_chars)),
            message_max_chars=int(
                getattr(settings, "A2A_MESSAGE_MAX_CHARS", cls.message_max_chars)
            ),
            inbox_max_messages=int(
                getattr(settings, "A2A_INBOX_MAX_MESSAGES", cls.inbox_max_messages)
            ),
        )


#: The shipped defaults, used wherever no limits are injected.
DEFAULT_LIMITS = A2ALimits()
