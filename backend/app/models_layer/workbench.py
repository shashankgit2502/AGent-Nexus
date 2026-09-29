"""Workbench gateway request shaping — headers and deployment-scoped base URL.

The Workbench provider is an **APIM-fronted gateway** that proxies to an
Azure-OpenAI-shaped endpoint. It is therefore reached with the ordinary OpenAI
client (``ChatOpenAI``), pointed at a deployment-scoped path, carrying the
gateway's own headers and an ``api-version`` query parameter:

    POST {base_url}/genai/azure/openai/deployments/{deployment}/chat/completions
         ?api-version={api_version}

    Ocp-Apim-Subscription-Key: <subscription key>     (or Authorization: Bearer …)
    x-kpmg-charge-code:        <charge code>          (required by the gateway)
    x-kpmg-region-override:    <region>               (optional)
    azureml-model-deployment:  <deployment>           (optional)
    Cache-Control:             no-cache

Ported verbatim (route shape and header names) from the reference implementation
``echolib/llm_client_builder_v2.py`` — ``_build_workbench_headers`` and
``_build_workbench_openai_base_url``. Nothing here is inferred: the header names
are what the gateway requires, so they are reproduced exactly rather than
generalised.

Pure functions, no I/O, no secret resolution — the caller passes an already
resolved key (ARCH §9.4).
"""

from __future__ import annotations

from urllib.parse import quote

from app.models_layer.connections import WorkbenchConfig

# The gateway's route prefix, between the connection base URL and the deployment.
_WORKBENCH_DEPLOYMENT_PATH = "/genai/azure/openai/deployments"

# The only Workbench child provider with an implemented API contract. The gateway
# also fronts Anthropic/Gemini, but those speak their own request shapes and
# cannot be driven by the OpenAI client — failing fast here is honest, whereas
# building an OpenAI-shaped request for them would 400 at the first real call.
SUPPORTED_WORKBENCH_PROVIDERS: frozenset[str] = frozenset({"openai"})


class UnsupportedWorkbenchProvider(ValueError):
    """The connection names a Workbench child provider we cannot construct."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Unsupported Workbench child provider {provider!r}. OpenAI is "
            "implemented; Anthropic/Gemini require their own Workbench API contract."
        )
        self.provider = provider


def build_workbench_base_url(base_url: str | None, deployment: str) -> str:
    """Build the deployment-scoped, OpenAI-compatible Workbench base URL.

    Args:
        base_url: the connection's gateway root (must be HTTPS).
        deployment: the catalog model's ``deployment_name``, falling back to its
            ``model_identifier``.

    Raises:
        ValueError: when the root or the deployment is missing, or the root is
            not HTTPS. A gateway carrying a subscription key over plaintext
            would leak it, so this is a hard failure rather than a warning.
    """
    root = (base_url or "").strip().rstrip("/")
    name = (deployment or "").strip()
    if not root:
        raise ValueError("base_url is required for the 'workbench' provider")
    if not root.lower().startswith("https://"):
        raise ValueError("Workbench base_url must use HTTPS")
    if not name:
        raise ValueError(
            "A deployment name (or model identifier) is required for the "
            "'workbench' provider — it is part of the gateway route"
        )
    if _WORKBENCH_DEPLOYMENT_PATH in root:
        # Already deployment-scoped (a registrar pasted the full path). Idempotent.
        return root
    return f"{root}{_WORKBENCH_DEPLOYMENT_PATH}/{quote(name, safe='')}"


def build_workbench_headers(
    api_key: str | None,
    config: WorkbenchConfig,
    *,
    authorization: str = "",
) -> dict[str, str]:
    """Build the Workbench gateway headers.

    ``api_key`` is the APIM **subscription key** (the gateway's normal auth).
    Callers holding a bearer token instead pass it through ``authorization``.

    Raises:
        ValueError: when neither credential is present — the gateway would
            answer an unauthenticated request with an opaque 401, so naming the
            missing field here is what makes the failure actionable.
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        # Required by the gateway for usage attribution; the placeholder default
        # lives on WorkbenchConfig so a connection that states none still builds.
        "x-kpmg-charge-code": str(config.charge_code or "0000"),
    }

    if authorization:
        headers["Authorization"] = authorization
    elif api_key:
        headers["Ocp-Apim-Subscription-Key"] = api_key
    else:
        raise ValueError(
            "Workbench credentials are required. Store the APIM subscription key "
            "as the connection's API key, or pass authorization='Bearer …'."
        )

    if config.region_override:
        headers["x-kpmg-region-override"] = config.region_override
    if config.azureml_model_deployment:
        headers["azureml-model-deployment"] = config.azureml_model_deployment

    return headers


def validate_workbench_provider(config: WorkbenchConfig) -> None:
    """Fail fast on a child provider we cannot construct a client for.

    Checked *before* any policy or header work so a bad configuration surfaces
    at build time with a named cause, rather than after a request has been
    assembled that the gateway cannot serve.
    """
    child = (config.workbench_provider or "openai").strip().lower()
    if child not in SUPPORTED_WORKBENCH_PROVIDERS:
        raise UnsupportedWorkbenchProvider(child)


__all__ = [
    "SUPPORTED_WORKBENCH_PROVIDERS",
    "UnsupportedWorkbenchProvider",
    "build_workbench_base_url",
    "build_workbench_headers",
    "validate_workbench_provider",
]
