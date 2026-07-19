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
} from "@/types/api";

// ── Connection ────────────────────────────────────────────────────────────────

export const PROVIDER_OPTIONS: readonly { value: Provider; label: string; needsBaseUrl: boolean }[] = [
  { value: "openai", label: "OpenAI", needsBaseUrl: false },
  { value: "anthropic", label: "Anthropic", needsBaseUrl: false },
  { value: "azure_openai", label: "Azure OpenAI", needsBaseUrl: true },
  { value: "ollama", label: "Ollama", needsBaseUrl: true },
  { value: "openrouter", label: "OpenRouter", needsBaseUrl: false },
  { value: "openai_compatible", label: "OpenAI-compatible", needsBaseUrl: true },
] as const;

export interface ConnectionFormState {
  displayName: string;
  provider: Provider;
  baseUrl: string;
  apiKeyRef: string;
  apiVersion: string;
}

export function initialConnectionForm(): ConnectionFormState {
  return { displayName: "", provider: "openai", baseUrl: "", apiKeyRef: "", apiVersion: "" };
}

function nullable(value: string): string | null {
  const t = value.trim();
  return t === "" ? null : t;
}

export function providerNeedsBaseUrl(provider: Provider): boolean {
  return PROVIDER_OPTIONS.find((p) => p.value === provider)?.needsBaseUrl ?? false;
}

export function validateConnection(state: ConnectionFormState): string | null {
  if (!state.displayName.trim()) return "Name the connection.";
  if (providerNeedsBaseUrl(state.provider) && !state.baseUrl.trim())
    return "This provider requires a base URL.";
  return null;
}

export function toConnectionCreate(state: ConnectionFormState): ConnectionCreate {
  return {
    display_name: state.displayName.trim(),
    provider: state.provider,
    base_url: nullable(state.baseUrl),
    api_key_ref: nullable(state.apiKeyRef),
    api_version: nullable(state.apiVersion),
  };
}

/** Prefill the connection form from an existing connection (edit mode, Bug 5).
 * The API key is never returned by the backend (write-only), so it starts blank;
 * leaving it blank on save keeps the stored key unchanged. */
export function connectionFormFromRead(conn: ConnectionRead): ConnectionFormState {
  return {
    displayName: conn.display_name,
    provider: conn.provider as Provider,
    baseUrl: conn.base_url ?? "",
    apiKeyRef: "",
    apiVersion: conn.api_version ?? "",
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
  };
  const key = state.apiKeyRef.trim();
  if (key !== "") update.api_key_ref = key;
  return update;
}

// ── Catalog model ─────────────────────────────────────────────────────────────

export interface CatalogFormState {
  providerConnectionId: string;
  displayName: string;
  modelIdentifier: string;
  modelType: ModelType;
  supportsTools: boolean;
  supportsStreaming: boolean;
  supportsVision: boolean;
  supportsReasoning: boolean;
  contextWindow: string;
}

export function initialCatalogForm(): CatalogFormState {
  return {
    providerConnectionId: "",
    displayName: "",
    modelIdentifier: "",
    modelType: "chat",
    supportsTools: true,
    supportsStreaming: true,
    supportsVision: false,
    supportsReasoning: false,
    contextWindow: "",
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
    supports_tools: supportsTools,
    supports_streaming: state.supportsStreaming,
    supports_vision: state.supportsVision,
    supports_reasoning: state.supportsReasoning,
    context_window: parseOptionalInt(state.contextWindow),
    source: "manual",
  };
}

// ── Inference profile ─────────────────────────────────────────────────────────

export interface ProfileFormState {
  name: string;
  defaultModelId: string;
  temperature: string;
  topP: string;
  maxTokens: string;
  reasoningLevel: string;
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
    reasoning_level: nullable(state.reasoningLevel),
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
