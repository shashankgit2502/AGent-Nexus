/**
 * REST DTOs — TypeScript mirror of `backend/app/schemas/*` (the source of truth).
 *
 * R4/R5: these mirror the Pydantic v2 models exactly (field names, optionality,
 * literal unions). UUIDs and datetimes are JSON strings over the wire. Optional
 * Pydantic fields (`X | None`) are modelled as `T | null` for *read* models
 * (the server always serialises the key) and `?` for *create/update* payloads
 * (the client may omit the key). Keep in lockstep with the backend schemas.
 */

// ── Primitive aliases (documentary) ───────────────────────────────────────────
/** A UUID serialised as a string. */
export type UUID = string;
/** An ISO-8601 datetime serialised as a string. */
export type ISODateTime = string;

// ── Teams (schemas/teams.py) ──────────────────────────────────────────────────
export interface TeamCreate {
  name: string;
  description?: string | null;
  goal_title?: string | null;
  goal_description?: string | null;
  success_criteria?: string[];
  /** Runtime embedding model for this team's knowledge/memory (ARCH §9.5). */
  embedding_model_id?: UUID | null;
}
export interface TeamUpdate {
  name?: string | null;
  description?: string | null;
  goal_title?: string | null;
  goal_description?: string | null;
  success_criteria?: string[] | null;
  embedding_model_id?: UUID | null;
}
export interface TeamRead {
  id: UUID;
  org_id: UUID;
  name: string;
  description: string | null;
  goal_title: string | null;
  goal_description: string | null;
  success_criteria: string[];
  embedding_model_id: UUID | null;
  created_at: ISODateTime;
}

// ── Agents (schemas/agents.py) ────────────────────────────────────────────────
/** capability toggle map → predefined tools (rag/web_search/code_interpreter/…). */
export type AgentCapabilities = Record<string, boolean>;

export interface AgentCreate {
  name: string;
  description?: string | null;
  instructions?: string | null;
  capabilities?: AgentCapabilities;
  memory_enabled?: boolean;
  profile_id?: UUID | null;
  override_model_id?: UUID | null;
  /** Per-agent embedding override for its private knowledge/memory (ARCH §9.5). */
  embedding_model_id?: UUID | null;
}
export interface AgentUpdate {
  name?: string | null;
  description?: string | null;
  instructions?: string | null;
  capabilities?: AgentCapabilities | null;
  memory_enabled?: boolean | null;
  profile_id?: UUID | null;
  override_model_id?: UUID | null;
  embedding_model_id?: UUID | null;
}
export interface AgentRead {
  id: UUID;
  org_id: UUID;
  team_id: UUID;
  name: string;
  description: string | null;
  instructions: string | null;
  capabilities: AgentCapabilities;
  memory_enabled: boolean;
  profile_id: UUID | null;
  override_model_id: UUID | null;
  embedding_model_id: UUID | null;
  created_at: ISODateTime;
}

// ── Sessions / runs (schemas/sessions.py) ─────────────────────────────────────
export interface SessionCreate {
  thread_id?: string | null;
}
export interface SessionRead {
  id: UUID;
  org_id: UUID;
  team_id: UUID;
  thread_id: string;
  status: string;
  created_at: ISODateTime;
}
export interface RunLaunch {
  query: string;
  max_rounds?: number;
  confidence_threshold?: number;
  deep_collaborate?: boolean;
}
export interface RunRead {
  id: UUID;
  org_id: UUID;
  session_id: UUID | null;
  conversation_id: UUID | null;
  query: string;
  rounds: number;
  converged: boolean;
  status: string;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
}
export interface RunLaunchResponse {
  run: RunRead;
  /** paused at the human gate, awaiting POST /sessions/{id}/resume. */
  interrupted: boolean;
  /** WS /sessions/{id}/stream?run_id=... */
  stream_url: string;
}
export type ResumeDecision = "approve" | "edit" | "reject";
export interface ResumeRequest {
  run_id: UUID;
  decision: ResumeDecision;
  content?: string | null;
  reason?: string | null;
}
export interface ArtifactRead {
  id: UUID;
  run_id: UUID;
  kind: string;
  content: string | null;
  content_format: string;
  created_at: ISODateTime;
}

// ── Providers / Model Resolution (schemas/providers.py) ───────────────────────
export type Provider =
  | "openai"
  | "anthropic"
  | "azure_openai"
  | "ollama"
  | "openrouter"
  | "openai_compatible";
export type ModelType = "chat" | "embedding";
export type ConnectionScope = "org" | "team";
export type CatalogSource = "discovered" | "models.dev" | "manual";

export interface ConnectionCreate {
  display_name: string;
  provider: Provider;
  base_url?: string | null;
  /** REFERENCE into the secrets manager — never the raw key (ARCH §9.4). */
  api_key_ref?: string | null;
  api_version?: string | null;
  scope?: ConnectionScope;
  team_id?: UUID | null;
}
export interface ConnectionRead {
  id: UUID;
  org_id: UUID;
  display_name: string;
  provider: string;
  base_url: string | null;
  api_version: string | null;
  scope: string;
  team_id: UUID | null;
  enabled: boolean;
  validated_at: ISODateTime | null;
  created_at: ISODateTime;
}
/** Partial edit for PUT /providers/connections/{id} (Bug 5). */
export interface ConnectionUpdate {
  display_name?: string;
  provider?: Provider;
  base_url?: string | null;
  api_key_ref?: string | null;
  api_version?: string | null;
  enabled?: boolean;
}
/** Result of POST /providers/connections/{id}/test (Bug 5). */
export interface ConnectionTestResult {
  ok: boolean;
  detail: string;
  models_found: number;
  validated_at: ISODateTime | null;
}
export interface CatalogModelCreate {
  provider_connection_id: UUID;
  display_name: string;
  model_identifier: string;
  model_type?: ModelType;
  deployment_name?: string | null;
  /** HARD GATE for mesh agents (ARCH §9.3). */
  supports_tools?: boolean;
  supports_streaming?: boolean;
  supports_vision?: boolean;
  supports_reasoning?: boolean;
  context_window?: number | null;
  source?: CatalogSource;
}
/** Partial edit for PATCH /providers/catalog/{id} — chiefly reclassify model_type. */
export interface CatalogModelUpdate {
  display_name?: string;
  model_type?: ModelType;
  supports_tools?: boolean;
  supports_streaming?: boolean;
  supports_vision?: boolean;
  supports_reasoning?: boolean;
  context_window?: number | null;
  enabled?: boolean;
}
export interface CatalogModelRead {
  id: UUID;
  org_id: UUID;
  provider_connection_id: UUID;
  display_name: string;
  model_identifier: string;
  model_type: string;
  deployment_name: string | null;
  supports_tools: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  supports_reasoning: boolean;
  context_window: number | null;
  source: string;
  enabled: boolean;
}
/** One page of a connection's catalog models (GET /providers/connections/{id}/models). */
export interface CatalogPage {
  items: CatalogModelRead[];
  total: number;
  limit: number;
  offset: number;
}
/** Query params for the master-detail model listing. */
export interface ConnectionModelsQuery {
  q?: string;
  supports_tools?: boolean;
  limit?: number;
  offset?: number;
}
export interface ProfileCreate {
  name: string;
  default_model_id?: UUID | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  reasoning_level?: string | null;
  json_mode?: boolean;
  streaming?: boolean;
}
export interface ProfileRead {
  id: UUID;
  org_id: UUID;
  name: string;
  default_model_id: UUID | null;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  reasoning_level: string | null;
  json_mode: boolean;
  streaming: boolean;
}

// ── Knowledge (schemas/knowledge.py) ──────────────────────────────────────────
export type KnowledgeKind = "file" | "url" | "db" | "team_doc";
/** Read-only DB connector config for kind='db' (Slice D): a DSN + a SELECT. */
export interface DbConnectorConfig {
  dsn: string;
  query: string;
}
export interface KnowledgeSourceCreate {
  kind: KnowledgeKind;
  uri?: string | null;
  display_name?: string | null;
  /** NULL = team-shared; set = agent-private (ARCH §10.5.1). */
  agent_id?: UUID | null;
  /** kind='db' read-only connector config ({dsn, query}). */
  connector_config?: DbConnectorConfig | null;
}
export type KnowledgeStatus = "pending" | "ingesting" | "ready" | "failed";
export interface KnowledgeSourceRead {
  id: UUID;
  org_id: UUID;
  team_id: UUID;
  agent_id: UUID | null;
  kind: string;
  uri: string | null;
  display_name: string | null;
  status: string;
  /** On a failed ingestion, the precise reason (ITEM 2) so the UI can show why. */
  error: string | null;
  chunk_count: number;
  created_at: ISODateTime;
}

// ── Memory (api/memory.py) ────────────────────────────────────────────────────
/** Rendered recall view: the private /memories/AGENTS.md rollup + shared layer. */
export interface AgentMemoryRead {
  agent_id: UUID;
  team_id: UUID;
  private: string | null;
  shared: string | null;
}

/** Memory Explorer record kinds → §14 sections (schemas/memory.py MemoryKind). */
export type MemoryKind = "fact" | "experience" | "session_learning" | "summary";

/** One structured long-term memory record (api/memory.py MemoryItemRead). */
export interface MemoryItemRead {
  id: UUID;
  kind: MemoryKind;
  content: string;
  pinned: boolean;
  created_at: string;
  run_id: UUID | null;
}

/** A page of memory records (api/memory.py MemoryPage). */
export interface MemoryPage {
  items: MemoryItemRead[];
  total: number;
  limit: number;
  offset: number;
}

/** Filters for listing an agent's memory records (GET /agents/{id}/memories). */
export interface MemoryListParams {
  kind?: MemoryKind;
  q?: string;
  pinned?: boolean;
  limit?: number;
  offset?: number;
}

// ── Chat / conversations (schemas/conversations.py) ───────────────────────────
/** connection/catalog/profile selector for no-team chat (ARCH §8.5.5). */
export type ModelRef = Record<string, unknown>;
export interface ConversationCreate {
  team_id?: UUID | null;
  model_ref?: ModelRef | null;
  title?: string | null;
  is_playground?: boolean;
  thread_id?: string | null;
}
export interface ConversationRead {
  id: UUID;
  org_id: UUID;
  team_id: UUID | null;
  model_ref: ModelRef | null;
  thread_id: string;
  title: string | null;
  is_playground: boolean;
  created_at: ISODateTime;
}
export interface MessageCreate {
  content: string;
  deep_collaborate?: boolean;
  /** Uploads this turn refers to (ARCH §8.5.3 / Bug 2); linked to the message server-side. */
  attachment_ids?: UUID[];
}
export interface MessageRead {
  id: UUID;
  conversation_id: UUID;
  role: string;
  content: string | null;
  run_id: UUID | null;
  deep_collaborate: boolean;
  created_at: ISODateTime;
}
export interface SendMessageResponse {
  assistant_message: MessageRead;
  run?: RunRead | null;
  stream_url?: string | null;
}
export type AttachmentScope = "transient" | "knowledge";
/** Ingestion lifecycle of an attachment's linked source (ARCH §8.5.3 / Bug 2). */
export type AttachmentStatus = "pending" | "ingesting" | "ready" | "failed";
export interface AttachmentRead {
  id: UUID;
  conversation_id: UUID;
  kind: string;
  uri: string;
  scope: AttachmentScope;
  source_id: UUID | null;
  /** Ingestion status of the linked source; null when there is none. */
  status: AttachmentStatus | null;
  error: string | null;
  promoted_source_id: UUID | null;
  created_at: ISODateTime;
}

// ── Dashboard (schemas/stats.py) ──────────────────────────────────────────────
export interface StatsRead {
  teams: number;
  agents: number;
  sessions: number;
  runs: number;
  completed_runs: number;
  conversations: number;
  knowledge_sources: number;
}
