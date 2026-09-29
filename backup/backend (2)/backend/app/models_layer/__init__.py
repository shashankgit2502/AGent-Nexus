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
    WorkbenchConfig,
)
from app.models_layer.errors import (
    ConnectionDisabled,
    EntityNotFound,
    ModelNotToolCapable,
    ModelResolutionError,
    NoModelConfigured,
    UnknownProvider,
    UnsupportedEmbeddingsProvider,
)
from app.models_layer.loader import load_conn_cat_repos
from app.models_layer.model_capabilities import (
    CLASSIC_POLICY,
    GATED_PROVIDERS,
    ModelFamily,
    ParameterPolicy,
    detect_profile,
    explain_model_failure,
    is_responses_unavailable,
    is_tool_reasoning_conflict,
    resolve_policy,
)
from app.models_layer.profiles import (
    InferenceProfile,
    InMemoryProfileRepository,
    ProfileRepository,
)
from app.models_layer.resolver import AgentModelRef, ModelResolver, resolve_model
from app.models_layer.responses_fallback import ResponsesFallback
from app.models_layer.translate_params import (
    NormalizedParams,
    Provider,
    ReasoningLevel,
    Verbosity,
    translate_params,
)
from app.models_layer.validation import ProbeResult, SSRFBlocked, probe_model, validate_base_url
from app.models_layer.workbench import (
    UnsupportedWorkbenchProvider,
    build_workbench_base_url,
    build_workbench_headers,
)

__all__ = [
    # translate_params
    "NormalizedParams",
    "Provider",
    "ReasoningLevel",
    "Verbosity",
    "translate_params",
    # model capabilities (GPT-5 family gate)
    "CLASSIC_POLICY",
    "GATED_PROVIDERS",
    "ModelFamily",
    "ParameterPolicy",
    "detect_profile",
    "resolve_policy",
    # GPT-5 runtime correction (Responses-API surface)
    "ResponsesFallback",
    "explain_model_failure",
    "is_responses_unavailable",
    "is_tool_reasoning_conflict",
    # workbench gateway
    "UnsupportedWorkbenchProvider",
    "WorkbenchConfig",
    "build_workbench_base_url",
    "build_workbench_headers",
    # db → domain repo loader
    "load_conn_cat_repos",
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
    "UnsupportedEmbeddingsProvider",
]
