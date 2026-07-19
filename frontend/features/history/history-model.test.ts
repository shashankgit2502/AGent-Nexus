/**
 * Unit test: History run-selection logic. A session lists its runs newest-first;
 * History must pick which run's artifact to show and avoid fetching one that can't
 * exist yet (a still-running run has no artifact → guaranteed 404).
 */
import { describe, it, expect } from "vitest";
import { terminalRun, hasArtifact } from "@/features/history/history-model";
import type { RunRead } from "@/types/api";

function run(overrides: Partial<RunRead>): RunRead {
  return {
    id: "r1",
    org_id: "o1",
    session_id: "s1",
    conversation_id: null,
    query: "q",
    rounds: 1,
    converged: true,
    status: "completed",
    started_at: "2026-06-20T00:00:00Z",
    finished_at: "2026-06-20T00:01:00Z",
    ...overrides,
  };
}

describe("terminalRun", () => {
  it("returns null for an empty list", () => {
    expect(terminalRun([])).toBeNull();
  });

  it("picks the first finished run (list is newest-first)", () => {
    const running = run({ id: "newest", status: "running", finished_at: null });
    const done = run({ id: "older", finished_at: "2026-06-19T00:00:00Z" });
    expect(terminalRun([running, done])?.id).toBe("older");
  });

  it("falls back to the newest run when none are finished", () => {
    const a = run({ id: "newest", status: "running", finished_at: null });
    const b = run({ id: "older", status: "running", finished_at: null });
    expect(terminalRun([a, b])?.id).toBe("newest");
  });
});

describe("hasArtifact", () => {
  it("is true only for a finished run", () => {
    expect(hasArtifact(null)).toBe(false);
    expect(hasArtifact(run({ finished_at: null }))).toBe(false);
    expect(hasArtifact(run({ finished_at: "2026-06-20T00:01:00Z" }))).toBe(true);
  });
});
