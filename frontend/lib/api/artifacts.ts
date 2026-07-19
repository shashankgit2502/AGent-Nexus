/**
 * Artifact REST client (ARTIFACTS.md §10) — detail, iterate, and version download.
 *
 * `getArtifact`/`iterateArtifact` go through the shared `apiFetch` (org headers, typed
 * errors). Downloads are **authenticated blob fetches** (org headers) rather than the
 * signed link, so any version downloads/previews uniformly without token-expiry — the
 * panel runs inside the authenticated app where the org context is available.
 */
import { apiFetch } from "@/lib/api/client";
import { orgHeaders } from "@/lib/org";
import type { ArtifactFileKind, ArtifactStatus } from "@/types/agui";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface ArtifactVersionDto {
  version: number;
  size_bytes: number | null;
  created_at: string;
}

export interface ArtifactDetailDto {
  id: string;
  kind: ArtifactFileKind;
  filename: string | null;
  mime_type: string | null;
  content_format: string;
  size_bytes: number | null;
  current_version: number;
  status: ArtifactStatus;
  preview: string | null;
  download_url: string;
  producer_agent_id: string | null;
  versions: ArtifactVersionDto[];
}

/** A run's artifact list item (§10 `GET /runs/{id}/artifacts`). `kind` includes the
 * run's terminal `synthesis`/`rejected` outcome alongside downloadable file kinds. */
export interface ArtifactReadDto {
  id: string;
  kind: ArtifactFileKind | "synthesis" | "rejected";
  filename: string | null;
  mime_type: string | null;
  content_format: string;
  size_bytes: number | null;
  current_version: number;
  status: ArtifactStatus;
  producer_agent_id: string | null;
  created_at: string;
}

/** The downloadable file kinds (excludes the `synthesis`/`rejected` run outcome). */
export const ARTIFACT_FILE_KINDS: ReadonlySet<string> = new Set<ArtifactFileKind>([
  "markdown",
  "code",
  "json",
  "csv",
  "docx",
  "xlsx",
  "pptx",
  "pdf",
  "image",
  "archive",
]);

/** List a run's artifacts (used by chat inline cards, §12). */
export function listRunArtifacts(runId: string): Promise<ArtifactReadDto[]> {
  return apiFetch<ArtifactReadDto[]>(`/runs/${runId}/artifacts`);
}

/** Metadata + version list + a fresh signed URL for one artifact (§10). */
export function getArtifact(id: string): Promise<ArtifactDetailDto> {
  return apiFetch<ArtifactDetailDto>(`/artifacts/${id}`);
}

/** Revise an artifact → a new version (Canvas edit/refine, §10). */
export function iterateArtifact(id: string, instruction: string): Promise<ArtifactDetailDto> {
  return apiFetch<ArtifactDetailDto>(`/artifacts/${id}/iterate`, {
    method: "POST",
    body: { instruction },
  });
}

function versionPath(id: string, version?: number): string {
  return version === undefined
    ? `/artifacts/${id}/download`
    : `/artifacts/${id}/versions/${version}/download`;
}

async function fetchArtifact(id: string, version?: number): Promise<Response> {
  const url = `${API_BASE_URL.replace(/\/$/, "")}${versionPath(id, version)}`;
  const response = await fetch(url, { headers: orgHeaders() });
  if (!response.ok) throw new Error(`artifact download failed (${response.status})`);
  return response;
}

/** The full text of a (version of an) artifact — for the preview pane + copy. */
export async function fetchArtifactText(id: string, version?: number): Promise<string> {
  return (await fetchArtifact(id, version)).text();
}

/** The raw bytes of a (version of an) artifact — for inline image preview. */
export async function fetchArtifactBlob(id: string, version?: number): Promise<Blob> {
  return (await fetchArtifact(id, version)).blob();
}

/** Save a (version of an) artifact to disk via an authenticated blob fetch. */
export async function downloadArtifactFile(
  id: string,
  filename: string,
  version?: number,
): Promise<void> {
  const blob = await (await fetchArtifact(id, version)).blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Open a (version of an) artifact in a new browser tab (read-only "open in editor"). */
export async function openArtifactInTab(id: string, version?: number): Promise<void> {
  const blob = await (await fetchArtifact(id, version)).blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  // Revoke after a delay so the new tab has loaded the blob.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
