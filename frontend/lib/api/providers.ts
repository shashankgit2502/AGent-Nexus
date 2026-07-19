/** Model Resolution Layer — connections / catalog / profiles (ARCH §14/§9/§27). */
import { apiFetch } from "@/lib/api/client";
import type {
  ConnectionCreate,
  ConnectionRead,
  ConnectionUpdate,
  ConnectionTestResult,
  CatalogModelCreate,
  CatalogModelRead,
  CatalogModelUpdate,
  CatalogPage,
  ConnectionModelsQuery,
  ProfileCreate,
  ProfileRead,
  UUID,
} from "@/types/api";

export const providersApi = {
  listConnections: () => apiFetch<ConnectionRead[]>("/providers/connections"),
  createConnection: (payload: ConnectionCreate) =>
    apiFetch<ConnectionRead>("/providers/connections", { method: "POST", body: payload }),
  updateConnection: (id: UUID, payload: ConnectionUpdate) =>
    apiFetch<ConnectionRead>(`/providers/connections/${id}`, { method: "PUT", body: payload }),
  deleteConnection: (id: UUID) =>
    apiFetch<void>(`/providers/connections/${id}`, { method: "DELETE" }),
  /** Run the validation probe on demand (Bug 5 — sets validated_at on success). */
  testConnection: (id: UUID) =>
    apiFetch<ConnectionTestResult>(`/providers/connections/${id}/test`, { method: "POST" }),
  /** Auto-discover the connection's models into the catalog (ARCH §27.2). */
  discoverConnection: (id: UUID) =>
    apiFetch<CatalogModelRead[]>(`/providers/connections/${id}/discover`, { method: "POST" }),
  /** One connection's models — searchable + paginated master-detail (ARCH §14, ITEM 1). */
  listConnectionModels: (id: UUID, query: ConnectionModelsQuery = {}) =>
    apiFetch<CatalogPage>(`/providers/connections/${id}/models`, {
      query: {
        q: query.q,
        supports_tools: query.supports_tools,
        limit: query.limit,
        offset: query.offset,
      },
    }),

  /** `supportsTools` filters to mesh-eligible chat models (ARCH §9.3 hard gate). */
  listCatalog: (supportsTools?: boolean) =>
    apiFetch<CatalogModelRead[]>("/providers/catalog", {
      query: { supports_tools: supportsTools },
    }),
  createCatalogModel: (payload: CatalogModelCreate) =>
    apiFetch<CatalogModelRead>("/providers/catalog", { method: "POST", body: payload }),
  /** Edit a catalog model — chiefly to reclassify model_type (chat↔embedding). */
  updateCatalogModel: (id: UUID, payload: CatalogModelUpdate) =>
    apiFetch<CatalogModelRead>(`/providers/catalog/${id}`, { method: "PATCH", body: payload }),
  deleteCatalogModel: (id: UUID) =>
    apiFetch<void>(`/providers/catalog/${id}`, { method: "DELETE" }),

  listProfiles: () => apiFetch<ProfileRead[]>("/providers/profiles"),
  createProfile: (payload: ProfileCreate) =>
    apiFetch<ProfileRead>("/providers/profiles", { method: "POST", body: payload }),
  /** Soft-delete a profile; 409 (ApiError) if agents still reference it (ITEM 1). */
  deleteProfile: (id: UUID) =>
    apiFetch<void>(`/providers/profiles/${id}`, { method: "DELETE" }),
};
