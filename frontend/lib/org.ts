/**
 * Org tenancy seam (TECHNICAL §11; backend `app/core/identity.py`).
 *
 * The backend resolves the active tenant from an optional `X-Org-Id` header,
 * falling back to a dev-seeded "default" org when the header is absent. A
 * malformed header is a 400 (backend validates), so we only send the header
 * when we actually have an org id — otherwise we let the backend default apply.
 * `X-User-Id` is likewise optional.
 *
 * This is the single place org context is read; every REST/WS call routes
 * through `orgHeaders()` / `withOrgQuery()`. Swapping the dev header scheme for
 * real IdP tokens later changes only this module.
 */

const ORG_ID_KEY = "nexagi.org_id";
const USER_ID_KEY = "nexagi.user_id";

function readLocal(key: string): string | null {
  if (typeof window === "undefined") return null; // SSR: no localStorage
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // storage disabled (private mode) — fall back to backend default
  }
}

/** The active org id, or `null` to use the backend's seeded default. */
export function getOrgId(): string | null {
  return readLocal(ORG_ID_KEY);
}

/** The active user id, or `null` when unauthenticated (dev). */
export function getUserId(): string | null {
  return readLocal(USER_ID_KEY);
}

/** Persist the active org/user context (e.g. after a future login). */
export function setOrgContext(orgId: string | null, userId: string | null = null): void {
  if (typeof window === "undefined") return;
  if (orgId) window.localStorage.setItem(ORG_ID_KEY, orgId);
  else window.localStorage.removeItem(ORG_ID_KEY);
  if (userId) window.localStorage.setItem(USER_ID_KEY, userId);
  else window.localStorage.removeItem(USER_ID_KEY);
}

/** Org/user headers for a REST request (omitted keys → backend default org). */
export function orgHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const orgId = getOrgId();
  if (orgId) headers["X-Org-Id"] = orgId;
  const userId = getUserId();
  if (userId) headers["X-User-Id"] = userId;
  return headers;
}
