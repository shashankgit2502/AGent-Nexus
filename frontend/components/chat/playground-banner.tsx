"use client";

/**
 * PlaygroundBanner (§9A.4) — marks an ephemeral team chat as NOT saved to
 * history. The backend excludes `is_playground` conversations from
 * `GET /conversations`, so this is the only signal the run is throwaway.
 */
import { FlaskConical } from "lucide-react";

export function PlaygroundBanner() {
  return (
    <div className="flex items-center gap-2 px-4 py-2 rounded-lg border border-amber-500/30 bg-amber-500/10">
      <FlaskConical className="w-3.5 h-3.5 text-amber-400 shrink-0" />
      <p className="text-[10.5px] font-mono text-amber-200/90 tracking-wide">
        Playground — ephemeral. This chat is <span className="font-bold">not saved</span> to history.
      </p>
    </div>
  );
}
