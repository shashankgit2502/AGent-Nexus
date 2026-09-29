/**
 * Pure Model-Resolution form logic (no React, no I/O). The 3-layer model
 * (Connection → Catalog → Inference Profile, ARCH §9/§27) has the most form
 * fields in the app, including numeric params that must be parsed/cleared
 * carefully — so the form→DTO mapping and validation live here, unit-tested in
 * node (R5: validate at the boundary; fail fast).
 *
 * Field shapes mirror `backend/app/schemas/providers.py` exactly (R4).
 */
import type {
  Provider,
  ConnectionCreate,
  ConnectionUpdate,
  ConnectionRead,
  CatalogModelCreate,
  ProfileCreate,
  ModelType,
  ModelFamily,
  ReasoningLevel,
  Verbosity,
  WorkbenchFields,
} from "@/types/api";

// ── Connection ────────────────────────────────────────────────────────────────

export const PROVIDER_OPTIONS: readonly { value: Provider; label: string; needsBaseUrl: boolean }[] = [
  { value: "openai", label: "OpenAI", needsBaseUrl: false },
  { value: "anthropic", label: "Anthropic", needsBaseUrl: false },
  { value: "azure_openai", label: "Azure OpenAI", needsBaseUrl: true },
  { value: "ollama", label: "Ollama", needsBaseUrl: true },
  { value: "openrouter", label: "OpenRouter", needsBaseUrl: false },
  { value: "openai_compatible", label: "OpenAI-compatible", needsBaseUrl: true },
  // APIM-fronted gateway. The base URL is the gateway root: the deployment-scoped
  // path is appended by the backend from the catalog model's deployment name.
  { value: "workbench", label: "Workbench (KPMG gateway)", needsBaseUrl: true },
] as const;

/** The underlying provider routed through the Workbench gateway. Only `openai`
 * has an implemented API contract — the others speak their own request shape and
 * are rejected by the backend with a named cause rather than failing at runtime. */
export const WORKBENCH_PROVIDER_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "openai", label: "OpenAI" },
] as const;

export interface ConnectionFormState {
  displayName: string;
  provider: Provider;
  baseUrl: string;
  apiKeyRef: string;
  apiVersion: string;
  // ── Workbench gateway settings (ignored by every other provider) ───────────
  workbenchProvider: string;
  chargeCode: string;
  regionOverride: string;
  azuremlModelDeployment: string;
}

export function initialConnectionForm(): ConnectionFormState {
  return {
    displayName: "",
    provider: "openai",
    baseUrl: "",
    apiKeyRef: "",
    apiVersion: "",
    workbenchProvider: "openai",
    chargeCode: "",
    regionOverride: "",
    azuremlModelDeployment: "",
  };
}

function nullable(value: string): string | null {
  const t = value.trim();
  return t === "" ? null : t;
}

export function providerNeedsBaseUrl(provider: Provider): boolean {
  return PROVIDER_OPTIONS.find((p) => p.value === provider)?.needsBaseUrl ?? false;
}

/** Whether to show the gateway fields. Kept as a helper so the panel and the
 * DTO builders agree on one rule. */
export function providerIsWorkbench(provider: Provider): boolean {
  return provider === "workbench";
}

/** The gateway fields, or `{}` for every other provider.
 *
 * Omitted entirely when the provider is not Workbench: the backend merges these
 * by key presence (`exclude_unset`), so sending explicit nulls would *clear*
 * stored gateway settings on an unrelated edit. */
function workbenchFields(state: ConnectionFormState): WorkbenchFields {
  if (!providerIsWorkbench(state.provider)) return {};
  return {
    workbench_provider: nullable(state.workbenchProvider),
    charge_code: nullable(state.chargeCode),
    region_override: nullable(state.regionOverride),
    azureml_model_deployment: nullable(state.azuremlModelDeployment),
  };
}

export function validateConnection(state: ConnectionFormState): string | null {
  if (!state.displayName.trim()) return "Name the connection.";
  if (providerNeedsBaseUrl(state.provider) && !state.baseUrl.trim())
    return "This provider requires a base URL.";
  if (providerIsWorkbench(state.provider)) {
    // The gateway carries a subscription key, so plaintext would leak it — the
    // backend refuses non-HTTPS outright; saying so here avoids a round-trip.
    if (!/^https:\/\//i.test(state.baseUrl.trim()))
      return "The Workbench base URL must use HTTPS.";
    if (!state.chargeCode.trim())
      return "A charge code is required for Workbench (sent as x-kpmg-charge-code).";
  }
  return null;
}

export function toConnectionCreate(state: ConnectionFormState): ConnectionCreate {
  return {
    display_name: state.displayName.trim(),
    provider: state.provider,
    base_url: nullable(state.baseUrl),
    api_key_ref: nullable(state.apiKeyRef),
    api_version: nullable(state.apiVersion),
    ...workbenchFields(state),
  };
}

/** Prefill the connection form from an existing connection (edit mode, Bug 5).
 * The API key is never returned by the backend (write-only), so it starts blank;
 * leaving it blank on save keeps the stored key unchanged. The gateway fields are
 * flattened onto the read DTO by the router, so they round-trip — without this
 * the edit form would open blank and a save would wipe the charge code. */
export function connectionFormFromRead(conn: ConnectionRead): ConnectionFormState {
  return {
    displayName: conn.display_name,
    provider: conn.provider as Provider,
    baseUrl: conn.base_url ?? "",
    apiKeyRef: "",
    apiVersion: conn.api_version ?? "",
    workbenchProvider: conn.workbench_provider ?? "openai",
    chargeCode: conn.charge_code ?? "",
    regionOverride: conn.region_override ?? "",
    azuremlModelDeployment: conn.azureml_model_deployment ?? "",
  };
}

/** Build a partial update DTO. A blank API key is omitted so editing other
 * fields does not wipe the stored credential. */
export function toConnectionUpdate(state: ConnectionFormState): ConnectionUpdate {
  const update: ConnectionUpdate = {
    display_name: state.displayName.trim(),
    provider: state.provider,
    base_url: nullable(state.baseUrl),
    api_version: nullable(state.apiVersion),
    ...workbenchFields(state),
  };
  const key = state.apiKeyRef.trim();
  if (key !== "") update.api_key_ref = key;
  return update;
}

// ── Catalog model ─────────────────────────────────────────────────────────────

/** `model_family` choices. `auto` is the default and means "detect from the
 * identifier + deployment name" — which is what every model registered before
 * this field existed resolves to, so leaving it alone changes nothing. */
export const MODEL_FAMILY_OPTIONS: readonly { value: ModelFamily; label: string }[] = [
  { value: "auto", label: "Auto-detect" },
  { value: "gpt4", label: "GPT-4 family and earlier (classic)" },
  { value: "gpt5", label: "GPT-5 family / o-series (reasoning)" },
] as const;

export interface CatalogFormState {
  providerConnectionId: string;
  displayName: string;
  modelIdentifier: string;
  modelType: ModelType;
  /** Azure routes by deployment, not model name; the Workbench gateway bakes it
   * into the request path. Blank falls back to the model identifier. */
  deploymentName: string;
  supportsTools: boolean;
  supportsStreaming: boolean;
  supportsVision: boolean;
  supportsReasoning: boolean;
  contextWindow: string;
  modelFamily: ModelFamily;
}

export function initialCatalogForm(): CatalogFormState {
  return {
    providerConnectionId: "",
    displayName: "",
    modelIdentifier: "",
    modelType: "chat",
    deploymentName: "",
    supportsTools: true,
    supportsStreaming: true,
    supportsVision: false,
    supportsReasoning: false,
    contextWindow: "",
    modelFamily: "auto",
  };
}

/** Parse a non-negative integer field; blank/invalid → null (cleared). */
export function parseOptionalInt(value: string): number | null {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && Number.isInteger(n) && n >= 0 ? n : null;
}

export function validateCatalog(state: CatalogFormState): string | null {
  if (!state.providerConnectionId) return "Pick the provider connection this model belongs to.";
  if (!state.displayName.trim()) return "Give the model a display name.";
  if (!state.modelIdentifier.trim()) return "Enter the provider model identifier.";
  if (state.contextWindow.trim() !== "" && parseOptionalInt(state.contextWindow) === null)
    return "Context window must be a non-negative integer.";
  return null;
}

export function toCatalogCreate(state: CatalogFormState): CatalogModelCreate {
  // embeddings are not tool-callers — never claim tool support for them.
  const supportsTools = state.modelType === "chat" ? state.supportsTools : false;
  return {
    provider_connection_id: state.providerConnectionId,
    display_name: state.displayName.trim(),
    model_identifier: state.modelIdentifier.trim(),
    model_type: state.modelType,
    deployment_name: nullable(state.deploymentName),
    supports_tools: supportsTools,
    supports_streaming: state.supportsStreaming,
    supports_vision: state.supportsVision,
    supports_reasoning: state.supportsReasoning,
    context_window: parseOptionalInt(state.contextWindow),
    // `auto` is the backend's "unstated" — sent as null so the column stays NULL
    // and the resolver detects from the names, exactly as before this field.
    model_family: state.modelFamily === "auto" ? null : state.modelFamily,
    source: "manual",
  };
}

// ── Inference profile ─────────────────────────────────────────────────────────

/**
 * `reasoning_level` choices. The backend pins these with a CHECK constraint and a
 * typed literal, so a free-text field here returns a 422 on any typo — which is
 * why this is a closed list rather than an input.
 *
 * `none` is not merely "fast": on gpt-5.1+ a Chat Completions request carrying
 * function tools fails unless the effort is none, because those models default to
 * one. `""` means unstated, which leaves the provider default in place.
 */
export const REASONING_LEVEL_OPTIONS: readonly { value: "" | ReasoningLevel; label: string }[] = [
  { value: "", label: "Not set (provider default)" },
  { value: "none", label: "none — no reasoning" },
  { value: "minimal", label: "minimal" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
  { value: "xhigh", label: "xhigh" },
  { value: "max", label: "max" },
] as const;

/** GPT-5 output-length control. Ignored by GPT-4-family models, which reject the
 * parameter — the backend withholds it for them rather than forwarding it. */
export const VERBOSITY_OPTIONS: readonly { value: "" | Verbosity; label: string }[] = [
  { value: "", label: "Not set (provider default)" },
  { value: "low", label: "low — terse" },
  { value: "medium", label: "medium — balanced" },
  { value: "high", label: "high — expansive" },
] as const;

export interface ProfileFormState {
  name: string;
  defaultModelId: string;
  temperature: string;
  topP: string;
  maxTokens: string;
  reasoningLevel: "" | ReasoningLevel;
  verbosity: "" | Verbosity;
  jsonMode: boolean;
  streaming: boolean;
}

export function initialProfileForm(): ProfileFormState {
  return {
    name: "",
    defaultModelId: "",
    temperature: "",
    topP: "",
    maxTokens: "",
    reasoningLevel: "",
    verbosity: "",
    jsonMode: false,
    streaming: true,
  };
}

/** Parse an optional float field in [min, max]; blank → null, invalid → null. */
export function parseOptionalFloat(value: string, min: number, max: number): number | null {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= min && n <= max ? n : null;
}

export function validateProfile(state: ProfileFormState): string | null {
  if (!state.name.trim()) return "Name the profile.";
  if (state.temperature.trim() !== "" && parseOptionalFloat(state.temperature, 0, 2) === null)
    return "Temperature must be between 0 and 2.";
  if (state.topP.trim() !== "" && parseOptionalFloat(state.topP, 0, 1) === null)
    return "top_p must be between 0 and 1.";
  if (state.maxTokens.trim() !== "" && parseOptionalInt(state.maxTokens) === null)
    return "max_tokens must be a non-negative integer.";
  return null;
}

export function toProfileCreate(state: ProfileFormState): ProfileCreate {
  return {
    name: state.name.trim(),
    default_model_id: state.defaultModelId.trim() === "" ? null : state.defaultModelId,
    temperature: parseOptionalFloat(state.temperature, 0, 2),
    top_p: parseOptionalFloat(state.topP, 0, 1),
    max_tokens: parseOptionalInt(state.maxTokens),
    reasoning_level: state.reasoningLevel === "" ? null : state.reasoningLevel,
    verbosity: state.verbosity === "" ? null : state.verbosity,
    json_mode: state.jsonMode,
    streaming: state.streaming,
  };
}

// ── Profile delete — 409 "in use by agents" parsing (ITEM 1) ───────────────────

/**
 * Pull the referencing-agent names out of a profile-delete 409 `detail` payload
 * (`{ message, agents: [{ id, name }] }`, backend `delete_profile`). Returns the
 * names, or `null` when the shape doesn't match — so the panel can build the
 * "reassign these agents first" message instead of showing a raw error. Pure +
 * defensive: untrusted shape is narrowed, never assumed (R5).
 */
export function parseInUseAgentNames(detail: unknown): string[] | null {
  if (!detail || typeof detail !== "object" || !("agents" in detail)) return null;
  const agents = (detail as { agents?: unknown }).agents;
  if (!Array.isArray(agents)) return null;
  return agents
    .map((a) =>
      a && typeof a === "object" && "name" in a ? String((a as { name: unknown }).name) : null,
    )
    .filter((n): n is string => n !== null);
}
