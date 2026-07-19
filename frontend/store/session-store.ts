/**
 * Session store (Zustand v5) — the live run's render state.
 *
 * This is a THIN wrapper: all event-folding logic lives in the pure
 * `applyEvent` reducer (`session-reducer.ts`); the store just holds the current
 * `RunState` and exposes actions. Components subscribe with selectors so a
 * single event only re-renders the panels that read the changed slice.
 *
 * R2: real primitive (Zustand `create`), no hand-rolled store. Streaming state
 * lives here and ONLY here — REST DTOs go through React Query (locked decision).
 */
import { create } from "zustand";
import type { AnyAGUIEvent } from "@/types/agui";
import {
  applyEvent,
  initialRunState,
  upsertArtifactEntry,
  type ArtifactEntry,
  type RunState,
} from "@/store/session-reducer";

interface SessionStore {
  run: RunState;
  /** Fold one streamed AG-UI event into the run state (dedup by seq is in the reducer). */
  ingest: (event: AnyAGUIEvent) => void;
  /** Fold an ordered batch (e.g. an initial replay snapshot). */
  ingestBatch: (events: readonly AnyAGUIEvent[]) => void;
  /**
   * Reflect a REST artifact mutation (iterate → new version, §10) into render state,
   * so the card in the Final Output stays in sync with the panel. Out-of-band from the
   * WS stream by design: iterate is a user REST action, not a streamed event.
   */
  updateArtifact: (entry: ArtifactEntry) => void;
  /** Clear back to an empty run (e.g. before launching/subscribing a new run). */
  reset: () => void;
}

export const useSessionStore = create<SessionStore>((set) => ({
  run: initialRunState(),
  ingest: (event) => set((state) => ({ run: applyEvent(state.run, event) })),
  ingestBatch: (events) =>
    set((state) => ({ run: events.reduce(applyEvent, state.run) })),
  updateArtifact: (entry) =>
    set((state) => ({
      run: { ...state.run, artifacts: upsertArtifactEntry(state.run.artifacts, entry) },
    })),
  reset: () => set({ run: initialRunState() }),
}));
