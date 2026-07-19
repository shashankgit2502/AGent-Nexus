/**
 * Pure History domain logic (no React, no I/O). A session has no run id of its
 * own, so History lists its runs and must pick which run's artifact to show. That
 * selection rule is the testable part — isolated here from the React Query hooks.
 */
import type { RunRead } from "@/types/api";

/**
 * Pick the run whose artifact History should show: the most recent run that
 * actually produced output. Runs arrive newest-first, so the first *finished* run
 * is the terminal one; fall back to the newest run (which may still be running and
 * thus have no artifact yet). Returns null for an empty list.
 */
export function terminalRun(runs: readonly RunRead[]): RunRead | null {
  return runs.find((r) => r.finished_at !== null) ?? runs[0] ?? null;
}

/** Only a finished run has an artifact to fetch (avoids a guaranteed 404). */
export function hasArtifact(run: RunRead | null): boolean {
  return run !== null && run.finished_at !== null;
}
