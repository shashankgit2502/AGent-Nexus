"""Model Resolution Layer (ARCHITECTURE.md §9 / §27).

Connection → Catalog → Inference Profile → resolve → ``init_chat_model``.
Public surface for the rest of the backend (agent factory, orchestrator,
synthesizer, Settings API).
"""

from app.models_layer.catalog import (
    CatalogModel,
    CatalogRepository,
    InMemoryCatalogRepository,
    ModelType,
)
from app.models_layer.connections import (
    ConnectionRepository,
    InMemoryConnectionRepository,
    LLMConnection,
)
from app.models_layer.errors import (
    ConnectionDisabled,
    EntityNotFound,
    ModelNotToolCapable,
    ModelResolutionError,
    NoModelConfigured,
    UnknownProvider,
)
from app.models_layer.profiles import (
    InferenceProfile,
    InMemoryProfileRepository,
    ProfileRepository,
)
from app.models_layer.resolver import AgentModelRef, ModelResolver, resolve_model
from app.models_layer.translate_params import (
    NormalizedParams,
    Provider,
    ReasoningLevel,
    translate_params,
)
from app.models_layer.validation import ProbeResult, SSRFBlocked, probe_model, validate_base_url

__all__ = [
    # translate_params
    "NormalizedParams",
    "Provider",
    "ReasoningLevel",
    "translate_params",
    # connections
    "LLMConnection",
    "ConnectionRepository",
    "InMemoryConnectionRepository",
    # catalog
    "CatalogModel",
    "CatalogRepository",
    "InMemoryCatalogRepository",
    "ModelType",
    # profiles
    "InferenceProfile",
    "ProfileRepository",
    "InMemoryProfileRepository",
    # resolver
    "AgentModelRef",
    "ModelResolver",
    "resolve_model",
    # validation
    "SSRFBlocked",
    "ProbeResult",
    "probe_model",
    "validate_base_url",
    # errors
    "ModelResolutionError",
    "UnknownProvider",
    "ModelNotToolCapable",
    "NoModelConfigured",
    "ConnectionDisabled",
    "EntityNotFound",
]
