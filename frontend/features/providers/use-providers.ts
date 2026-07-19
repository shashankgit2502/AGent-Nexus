"use client";

/**
 * Model-Resolution REST hooks (React Query) — connections / catalog / profiles
 * (ARCH §9/§27, `GET|POST /providers/*`). Mutations invalidate the matching
 * list key so the 3-layer Settings→AI screen refreshes after each create.
 *
 * `useProfiles` here is the canonical inference-profile read (key `["profiles"]`),
 * shared with the no-team chat picker and the Agent Builder profile selector.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { providersApi } from "@/lib/api/providers";
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

const CONNECTIONS_KEY = ["connections"] as const;
const PROFILES_KEY = ["profiles"] as const;

export function useConnections() {
  return useQuery({ queryKey: CONNECTIONS_KEY, queryFn: () => providersApi.listConnections() });
}

export function useCreateConnection() {
  const qc = useQueryClient();
  return useMutation<ConnectionRead, Error, ConnectionCreate>({
    mutationFn: (payload) => providersApi.createConnection(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONNECTIONS_KEY }),
  });
}

export function useUpdateConnection() {
  const qc = useQueryClient();
  return useMutation<ConnectionRead, Error, { id: UUID; payload: ConnectionUpdate }>({
    mutationFn: ({ id, payload }) => providersApi.updateConnection(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONNECTIONS_KEY }),
  });
}

export function useDeleteConnection() {
  const qc = useQueryClient();
  return useMutation<void, Error, UUID>({
    mutationFn: (id) => providersApi.deleteConnection(id),
    // Removing a connection also drops it from the Catalog master list and its
    // (now-hidden) models, so refresh those views too.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONNECTIONS_KEY });
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["connection-models"] });
    },
  });
}

/** Validation probe on demand (Bug 5). Refreshes the connections list so the
 * validated/pending pill updates after a successful test. */
export function useTestConnection() {
  const qc = useQueryClient();
  return useMutation<ConnectionTestResult, Error, UUID>({
    mutationFn: (id) => providersApi.testConnection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONNECTIONS_KEY }),
  });
}

/** Discover models into the catalog (ARCH §27.2). Invalidates both the catalog
 * (new models) and connections (the discover also validates the connection). */
export function useDiscoverConnection() {
  const qc = useQueryClient();
  return useMutation<CatalogModelRead[], Error, UUID>({
    mutationFn: (id) => providersApi.discoverConnection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["connection-models"] });
      qc.invalidateQueries({ queryKey: CONNECTIONS_KEY });
    },
  });
}

/** Catalog models, optionally filtered to `supports_tools` (mesh-eligible). */
export function useCatalog(supportsTools?: boolean) {
  return useQuery({
    queryKey: ["catalog", supportsTools ?? "all"],
    queryFn: () => providersApi.listCatalog(supportsTools),
  });
}

export function useCreateCatalogModel() {
  const qc = useQueryClient();
  return useMutation<CatalogModelRead, Error, CatalogModelCreate>({
    mutationFn: (payload) => providersApi.createCatalogModel(payload),
    // any catalog filter view + the connection's master-detail page may now be stale.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["connection-models"] });
    },
  });
}

/** Edit a catalog model (reclassify model_type chat↔embedding, ARCH §9.5 / Approach B).
 * Invalidates the catalog (the team embedding picker reads it) + the connection's models. */
export function useUpdateCatalogModel() {
  const qc = useQueryClient();
  return useMutation<CatalogModelRead, Error, { id: UUID; payload: CatalogModelUpdate }>({
    mutationFn: ({ id, payload }) => providersApi.updateCatalogModel(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["connection-models"] });
    },
  });
}

export function useDeleteCatalogModel() {
  const qc = useQueryClient();
  return useMutation<void, Error, UUID>({
    mutationFn: (id) => providersApi.deleteCatalogModel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["connection-models"] });
    },
  });
}

/**
 * One connection's models, lazily (master-detail, ARCH §14, ITEM 1). `enabled`
 * gates the fetch so a collapsed connection costs nothing; the query key carries
 * the search/filter/page params so each refinement is its own cache entry, and
 * `keepPreviousData` avoids a flash of empty while a new search resolves.
 */
export function useConnectionModels(
  connectionId: UUID,
  query: ConnectionModelsQuery,
  enabled: boolean,
) {
  return useQuery<CatalogPage>({
    queryKey: ["connection-models", connectionId, query],
    queryFn: () => providersApi.listConnectionModels(connectionId, query),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useProfiles() {
  return useQuery({ queryKey: PROFILES_KEY, queryFn: () => providersApi.listProfiles() });
}

/** Delete a profile. The mutation surfaces the 409-in-use `ApiError` to the caller
 * (so the panel can list the blocking agents); on success it refreshes the list. */
export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation<void, Error, UUID>({
    mutationFn: (id) => providersApi.deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROFILES_KEY }),
  });
}

export function useCreateProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileRead, Error, ProfileCreate>({
    mutationFn: (payload) => providersApi.createProfile(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROFILES_KEY }),
  });
}
