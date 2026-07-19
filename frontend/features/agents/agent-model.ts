/**
 * Pure agent-form domain logic (no React, no I/O) — the high-risk mapping in the
 * Agent Builder. Form state ↔ `AgentCreate`/`AgentUpdate` DTOs, capability toggle
 * mapping, and boundary validation live here so they are unit-testable in a node
 * env (R3/R5) without rendering. The dialog stays a thin wrapper.
 *
 * Source of truth for capability keys (R1/R4): `backend/app/agents/config.py`
 * `Capabilities` — exactly these five keys are honoured (snapshot.py filters the
 * `capabilities` dict to `Capabilities.model_fields`). We offer no others.
 */
import type { AgentCreate, AgentUpdate, AgentRead, AgentCapabilities } from "@/types/api";

export interface CapabilitySpec {
  key: string;
  label: string;
  hint: string;
}

/** The five real capability toggles → predefined tools (ARCH §10.5.4). */
export const CAPABILITY_CATALOG: readonly CapabilitySpec[] = [
  { key: "rag", label: "Knowledge retrieval (RAG)", hint: "search_knowledge over the team / agent KB" },
  { key: "web_search", label: "Web search", hint: "live web-search tool" },
  { key: "code_interpreter", label: "Code interpreter", hint: "sandboxed code execution" },
  { key: "doc_chart", label: "Docs & charts", hint: "document / chart generation" },
  { key: "image_gen", label: "Image generation", hint: "image-generation tool" },
] as const;

/** Editable Agent Builder form state. */
export interface AgentFormState {
  name: string;
  description: string;
  instructions: string;
  capabilities: AgentCapabilities;
  memoryEnabled: boolean;
  profileId: string;
  overrideModelId: string;
}

/** A blank form (Create), or one seeded from an existing agent (Edit). */
export function initialAgentForm(agent?: AgentRead): AgentFormState {
  return {
    name: agent?.name ?? "",
    description: agent?.description ?? "",
    instructions: agent?.instructions ?? "",
    capabilities: { ...(agent?.capabilities ?? {}) },
    memoryEnabled: agent?.memory_enabled ?? false,
    profileId: agent?.profile_id ?? "",
    overrideModelId: agent?.override_model_id ?? "",
  };
}

/** Immutable capability toggle (coding-style: never mutate). */
export function toggleCapability(
  caps: AgentCapabilities,
  key: string,
  on: boolean,
): AgentCapabilities {
  return { ...caps, [key]: on };
}

export function isCapabilityOn(caps: AgentCapabilities, key: string): boolean {
  return caps[key] === true;
}

/** Keep only the real, enabled capability keys (drops stale/false flags). */
export function enabledCapabilities(caps: AgentCapabilities): AgentCapabilities {
  const known = new Set(CAPABILITY_CATALOG.map((c) => c.key));
  const out: AgentCapabilities = {};
  for (const spec of CAPABILITY_CATALOG) {
    if (caps[spec.key] === true && known.has(spec.key)) out[spec.key] = true;
  }
  return out;
}

/**
 * Validate the form at the client boundary; returns an error string or null.
 *
 * An inference profile is REQUIRED: it supplies the agent's model, and the
 * backend has no "team default profile" fallback — a profile-less agent forces
 * the whole run onto the deterministic stub path (snapshot.py `_SnapshotIncomplete`),
 * so we refuse to create one here rather than ship a silently-unrunnable agent.
 */
export function validateAgentForm(state: AgentFormState): string | null {
  if (!state.name.trim()) return "Give the agent a name.";
  if (!state.profileId.trim()) {
    return "Select an inference profile — it provides the agent's model.";
  }
  return null;
}

/**
 * Read access to the model-capability facts the form needs to pre-check §9.3 on the
 * client (joined from `useProfiles` + `useCatalog`). Kept as an interface (not the raw
 * arrays) so the logic is pure and unit-testable without the data hooks.
 */
export interface ModelCapabilityLookup {
  /** Profile id → its default model id (`null`/`undefined` when none / not loaded). */
  profileDefaultModelId: (profileId: string) => string | null | undefined;
  /** Model id → `supports_tools` (`undefined` when the model isn't in the catalog). */
  modelSupportsTools: (modelId: string) => boolean | undefined;
}

/** The agent's effective model id = override (ARCH Q1) else the profile's default model. */
export function effectiveModelId(
  state: AgentFormState,
  lookup: ModelCapabilityLookup,
): string | null {
  const override = state.overrideModelId.trim();
  if (override) return override;
  const profileId = state.profileId.trim();
  if (!profileId) return null;
  return lookup.profileDefaultModelId(profileId) ?? null;
}

/**
 * Client-side §9.3 pre-check (mirrors the backend config-time gate): a warning string
 * when the effective model is KNOWN to be non-tool-capable, else `null`. Unknown
 * capability (catalog not loaded yet) returns `null` — the backend 422 stays the
 * authority, so we never block on missing data, only on a confirmed non-tool model.
 */
export function toolCapabilityWarning(
  state: AgentFormState,
  lookup: ModelCapabilityLookup,
): string | null {
  const modelId = effectiveModelId(state, lookup);
  if (!modelId) return null;
  if (lookup.modelSupportsTools(modelId) === false) {
    return (
      "This model can't call tools — peer agents need a tool-capable model (ARCH §9.3). " +
      "Pick a different profile, or set a tool-capable override model."
    );
  }
  return null;
}

/** Trim a free-text field to a nullable value (empty → null). */
function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** Map the form to a `POST /teams/{id}/agents` payload. */
export function toAgentCreate(state: AgentFormState): AgentCreate {
  return {
    name: state.name.trim(),
    description: nullable(state.description),
    instructions: nullable(state.instructions),
    capabilities: enabledCapabilities(state.capabilities),
    memory_enabled: state.memoryEnabled,
    profile_id: nullable(state.profileId),
    override_model_id: nullable(state.overrideModelId),
  };
}

/**
 * Map the form to a `PUT /agents/{id}` payload. The backend update is partial
 * (only provided fields change); we send the full editable set so the form is
 * the authority on the agent's current config.
 */
export function toAgentUpdate(state: AgentFormState): AgentUpdate {
  return {
    name: state.name.trim(),
    description: nullable(state.description),
    instructions: nullable(state.instructions),
    capabilities: enabledCapabilities(state.capabilities),
    memory_enabled: state.memoryEnabled,
    profile_id: nullable(state.profileId),
    override_model_id: nullable(state.overrideModelId),
  };
}

/** A compact summary of enabled capabilities for list rows. */
export function capabilitySummary(caps: AgentCapabilities): string[] {
  return CAPABILITY_CATALOG.filter((c) => caps[c.key] === true).map((c) => c.label);
}
