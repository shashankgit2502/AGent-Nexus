/**
 * Unit test: the pure Memory Explorer section grouping (FRONTEND_SPEC §14).
 *
 * Node env, no DOM/React — verifies records group into the §14 sections in section
 * order, empty sections drop out, and within-section order is preserved (the
 * backend's pinned-first/newest ordering passes through untouched).
 */
import { describe, it, expect } from "vitest";
import { MEMORY_SECTIONS, groupByKind } from "@/features/memory/memory-model";
import type { MemoryItemRead, MemoryKind } from "@/types/api";

function rec(id: string, kind: MemoryKind, content = id): MemoryItemRead {
  return { id, kind, content, pinned: false, created_at: "2026-06-21T00:00:00Z", run_id: null };
}

describe("memory section grouping", () => {
  it("defines the four §14 sections in order", () => {
    expect(MEMORY_SECTIONS.map((s) => s.kind)).toEqual([
      "fact",
      "experience",
      "session_learning",
      "summary",
    ]);
  });

  it("groups records into their sections, dropping empty ones", () => {
    const grouped = groupByKind([rec("a", "fact"), rec("b", "summary"), rec("c", "fact")]);
    expect(grouped.map((g) => g.kind)).toEqual(["fact", "summary"]); // experience/session empty → dropped
    const facts = grouped.find((g) => g.kind === "fact");
    expect(facts?.items.map((i) => i.id)).toEqual(["a", "c"]); // order preserved
  });

  it("returns an empty array when there are no records", () => {
    expect(groupByKind([])).toEqual([]);
  });
});
