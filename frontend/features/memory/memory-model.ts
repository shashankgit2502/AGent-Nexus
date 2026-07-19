/**
 * Pure Memory Explorer view logic (FRONTEND_SPEC §14).
 *
 * The §14 sections and the grouping of an agent's records into them, kept out of
 * the React component so they are unit-testable (the project's `*-model.ts`
 * pattern). Ordering within a section is preserved from the backend (pinned-first,
 * then newest — see `MemoryItemStore.list_items`).
 */
import type { MemoryItemRead, MemoryKind } from "@/types/api";

export interface MemorySection {
  kind: MemoryKind;
  label: string;
  hint: string;
}

/** The §14 sections, in display order, mapped to backend memory kinds (§25.2). */
export const MEMORY_SECTIONS: readonly MemorySection[] = [
  { kind: "fact", label: "Facts", hint: "Semantic — durable facts the agent knows" },
  { kind: "experience", label: "Experiences", hint: "Episodic — findings from past runs" },
  {
    kind: "session_learning",
    label: "Session Learnings",
    hint: "Distilled per-session learnings",
  },
  { kind: "summary", label: "Summaries", hint: "Consolidated summaries" },
];

export interface GroupedSection extends MemorySection {
  items: MemoryItemRead[];
}

/**
 * Group records into the §14 sections, in section order, preserving each section's
 * incoming item order. Empty sections are dropped so the UI only renders sections
 * that have content.
 */
export function groupByKind(items: MemoryItemRead[]): GroupedSection[] {
  return MEMORY_SECTIONS.map((section) => ({
    ...section,
    items: items.filter((item) => item.kind === section.kind),
  })).filter((section) => section.items.length > 0);
}
