/**
 * Typed REST client core (ARCH §14).
 *
 * One thin `apiFetch<T>` wraps `fetch`: it resolves the base URL from
 * `NEXT_PUBLIC_API_BASE_URL`, injects org headers (`lib/org.ts`), JSON-encodes
 * bodies, and turns non-2xx responses into a typed `ApiError` carrying the
 * backend's `detail` (R5: handle errors explicitly; never swallow). Resource
 * modules (`lib/api/teams.ts`, …) build on this — they hold no fetch logic.
 *
 * Streaming is deliberately NOT here: AG-UI events flow through `lib/ws` into
 * the Zustand store, never the REST layer (locked decision — never mix).
 */
import { orgHeaders } from "@/lib/org";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** A failed REST call (non-2xx). `detail` is the backend's error message. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON body — serialised automatically; omit for GET/DELETE. */
  body?: unknown;
  /** Extra query params (string values). */
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path.replace(/^\//, ""), `${BASE_URL.replace(/\/$/, "")}/`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseError(response: Response): Promise<ApiError> {
  let detail: unknown = null;
  try {
    const body = await response.json();
    detail = (body as { detail?: unknown })?.detail ?? body;
  } catch {
    // non-JSON error body — keep detail null, fall back to status text
  }
  const message =
    typeof detail === "string" ? detail : `${response.status} ${response.statusText}`;
  return new ApiError(response.status, detail, message);
}

/** Perform an org-scoped JSON request, returning the parsed `T` (or `void`). */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const headers: Record<string, string> = { ...orgHeaders() };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!response.ok) throw await parseError(response);

  // 204 No Content (e.g. DELETE) — nothing to parse.
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Org-scoped multipart upload (e.g. chat attachments, ARCH §8.5.3).
 *
 * Separate from `apiFetch` because the browser must set the `multipart/form-data`
 * boundary itself — so we deliberately do NOT set `Content-Type` and do NOT
 * JSON-encode. Shares the same URL builder, org headers, and typed error path.
 */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(buildUrl(path), {
    method: "POST",
    headers: { ...orgHeaders() }, // no Content-Type → browser adds the boundary
    body: form,
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

/** The configured REST base URL (exported for diagnostics / WS url derivation). */
export const apiBaseUrl = BASE_URL;
