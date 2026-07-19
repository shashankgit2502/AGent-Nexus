/**
 * Artifact helpers — resolve the backend's relative, signed download path to an
 * absolute URL and format human-readable sizes (ARTIFACTS.md §10/§12).
 *
 * The backend descriptor carries a **relative** `download_url`
 * (`/artifacts/{id}/download?token=…`) — signed + RLS-scoped, so it works as a
 * plain header-less link; `Content-Disposition: attachment` makes the browser
 * download even cross-origin (the `download` attr is ignored cross-origin). We only
 * prefix the API base, mirroring `lib/api/client.ts`.
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Absolute download URL for a (possibly relative) signed artifact path. */
export function artifactDownloadUrl(downloadUrl: string): string {
  if (/^https?:\/\//i.test(downloadUrl)) return downloadUrl;
  return `${API_BASE_URL.replace(/\/$/, "")}/${downloadUrl.replace(/^\//, "")}`;
}

/** Compact byte size (e.g. `1.4 KB`); `null`/0 → `—`. */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`;
}
