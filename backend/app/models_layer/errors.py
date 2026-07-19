"""Typed errors for the Model Resolution Layer (ARCHITECTURE.md §9/§27).

Each failure mode in the resolution chain gets a distinct exception so callers
(the agent factory, the orchestrator/synthesizer model lookups, and the Settings
API in Step 9) can react precisely instead of catching a bare ``Exception`` —
which R3 forbids as an error-swallowing band-aid.
"""

from __future__ import annotations


class ModelResolutionError(Exception):
    """Base class for every Model Resolution Layer failure."""


class UnknownProvider(ModelResolutionError):
    """A connection names a provider the layer does not know how to resolve."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Unknown provider {provider!r}; not in the supported provider set")
        self.provider = provider


class ModelNotToolCapable(ModelResolutionError):
    """A mesh agent requested a model whose ``supports_tools`` flag is false.

    This is the §9.3 hard gate: ReAct mesh agents must call tools, so a
    non-tool-capable model is rejected. The Synthesizer relaxes this
    (``require_tools=False``) and may use a cheaper non-tool model.
    """

    def __init__(self, model_display_name: str) -> None:
        super().__init__(
            f"Model {model_display_name!r} does not support tool calling; "
            "mesh agents require a tool-capable model (ARCH §9.3)"
        )
        self.model_display_name = model_display_name


class NotAnEmbeddingModel(ModelResolutionError):
    """A catalog model resolved for embeddings is not ``model_type='embedding'``.

    The embeddings resolver (ARCH §9.5) only accepts catalog rows flagged as
    embedding models; resolving a chat model here is a configuration error we
    surface explicitly rather than letting ``init_embeddings`` fail opaquely (R3).
    """

    def __init__(self, model_display_name: str) -> None:
        super().__init__(
            f"Model {model_display_name!r} is not an embedding model "
            "(model_type must be 'embedding'; ARCH §9.5)"
        )
        self.model_display_name = model_display_name


class NoModelConfigured(ModelResolutionError):
    """Neither an agent override nor the profile default resolved to a model id."""


class ConnectionDisabled(ModelResolutionError):
    """The resolved connection is disabled and must not be used at runtime."""

    def __init__(self, display_name: str) -> None:
        super().__init__(f"Connection {display_name!r} is disabled")
        self.display_name = display_name


class EntityNotFound(ModelResolutionError):
    """A referenced connection / catalog model / profile id does not exist."""

    def __init__(self, kind: str, entity_id: object) -> None:
        super().__init__(f"{kind} {entity_id!r} not found")
        self.kind = kind
        self.entity_id = entity_id
