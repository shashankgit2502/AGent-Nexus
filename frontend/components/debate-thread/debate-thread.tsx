"use client";

/**
 * Debate panel (§9.4) — a PR-review thread, not a console log. Each item is a
 * real AG-UI event: a `contribution` (a "comment" with a confidence badge) or a
 * `critique` (a "requested changes" review, colour-coded by severity, sender →
 * target). Items animate in (fade + slide-up ~300ms). Built from the pure
 * `buildDebateTimeline`, so the order is event-derived and deterministic.
 */
import { useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessagesSquare, MessageSquareOff } from "lucide-react";
import { useSessionStore } from "@/store/session-store";
import {
  buildDebateTimeline,
  type AgentLabel,
  type DebateItem,
} from "@/components/agent-graph/graph-model";
import { ContentBlocks } from "@/components/content-blocks/content-block";
import type { A2AIntent, CritiqueSeverity } from "@/types/agui";

const SEVERITY_STYLE: Record<CritiqueSeverity, string> = {
  minor: "bg-amber-500/10 text-amber-400 border-amber-500/25",
  major: "bg-orange-500/10 text-orange-400 border-orange-500/25",
  blocking: "bg-rose-500/10 text-rose-400 border-rose-500/25",
};

/**
 * Per-intent styling (ARCH §23.3). Colour is the fastest way to read *what kind of
 * exchange* this was without parsing the text: amber = someone is blocked, violet = work
 * changed hands, emerald = agreement, sky = a shared finding. Matches the A2A edge colours
 * on the graph so the two views read as one system.
 */
const INTENT_STYLE: Record<A2AIntent, { text: string; border: string; badge: string }> = {
  REQUEST: {
    text: "text-amber-400",
    border: "border-amber-900/40",
    badge: "bg-amber-500/10 text-amber-400 border-amber-500/25",
  },
  DELEGATE: {
    text: "text-violet-400",
    border: "border-violet-900/40",
    badge: "bg-violet-500/10 text-violet-400 border-violet-500/25",
  },
  ENDORSE: {
    text: "text-emerald-400",
    border: "border-emerald-900/40",
    badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  },
  INFORM: {
    text: "text-sky-400",
    border: "border-sky-900/40",
    badge: "bg-sky-500/10 text-sky-400 border-sky-500/25",
  },
  PROPOSE: {
    text: "text-indigo-400",
    border: "border-indigo-900/40",
    badge: "bg-indigo-500/10 text-indigo-400 border-indigo-500/25",
  },
  CRITIQUE: {
    text: "text-rose-400",
    border: "border-rose-900/40",
    badge: "bg-rose-500/10 text-rose-400 border-rose-500/25",
  },
  // Never rendered as a thread row (a ballot has no body — see `buildDebateTimeline`),
  // but kept so the map is exhaustive over the intent union.
  VOTE: {
    text: "text-teal-400",
    border: "border-teal-900/40",
    badge: "bg-teal-500/10 text-teal-400 border-teal-500/25",
  },
};

interface DebateThreadProps {
  labels: Record<string, AgentLabel>;
}

export function DebateThread({ labels }: DebateThreadProps) {
  // Select the raw run (stable reference) then derive the timeline in useMemo.
  // Computing buildDebateTimeline *inside* the selector returns a new array each
  // call, which trips useSyncExternalStore's "getSnapshot should be cached"
  // infinite-loop guard (Zustand compares snapshots by Object.is).
  const run = useSessionStore((s) => s.run);
  const items = useMemo(() => buildDebateTimeline(run), [run]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [items.length]);

  const name = (id: string) => labels[id]?.name ?? id;

  return (
    <div className="w-full h-full bg-[#18181b] rounded-xl border border-[#27272a] overflow-hidden flex flex-col">
      <div className="px-4 py-3 border-b border-[#27272a] flex items-center justify-between bg-[#111113]">
        <div className="flex items-center gap-2">
          <MessagesSquare className="w-4 h-4 text-emerald-400" />
          <span className="text-[11px] font-bold tracking-wider text-zinc-400 uppercase">
            Debate Thread
          </span>
        </div>
        <span className="text-[9px] text-zinc-500 bg-zinc-800/60 px-2 py-0.5 rounded-full font-mono">
          {items.length} events
        </span>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-3 min-h-[220px]"
      >
        {items.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500">
            <MessageSquareOff className="w-8 h-8 opacity-20 mb-2" />
            <p className="text-xs">No contributions yet</p>
            <p className="text-[10px] text-zinc-600 mt-1">Agents post here as the round runs</p>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {items.map((item) => (
              <DebateItemView key={item.key} item={item} name={name} />
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}

function DebateItemView({
  item,
  name,
}: {
  item: DebateItem;
  name: (id: string) => string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`p-3 rounded-lg border bg-[#111113]/70 ${
        item.kind === "critique"
          ? "border-rose-900/30"
          : item.kind === "message"
            ? INTENT_STYLE[item.intent].border
            : "border-zinc-800/80"
      }`}
    >
      {item.kind === "message" ? (
        <>
          <div className="flex items-center justify-between mb-1.5 gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={`text-[11px] font-semibold ${INTENT_STYLE[item.intent].text}`}>
                {name(item.sender)}
              </span>
              <span className="text-[9px] text-zinc-600 font-mono truncate">
                {item.recipients === null
                  ? "→ everyone"
                  : `→ ${item.recipients.map(name).join(", ")}`}{" "}
                · Round {item.round}
              </span>
            </div>
            <span
              className={`shrink-0 text-[8px] px-1.5 py-0.5 rounded-full border font-mono font-bold uppercase ${INTENT_STYLE[item.intent].badge}`}
            >
              {item.intent}
            </span>
          </div>
          <p className="text-[11.5px] leading-relaxed text-zinc-300 font-sans tracking-wide whitespace-pre-wrap">
            {item.body}
          </p>
          {item.sourceUrls.length > 0 ? (
            /* An INFORM's whole value is that a peer can CITE it rather than
               re-research it — dropping the sources here would defeat the intent. */
            <ul className="mt-1.5 flex flex-col gap-0.5">
              {item.sourceUrls.map((url) => (
                <li key={url} className="truncate">
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-[10px] font-mono text-sky-400/80 hover:text-sky-300 underline underline-offset-2"
                  >
                    {url}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : item.kind === "contribution" ? (
        <>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-emerald-400">{name(item.author)}</span>
              <span className="text-[9px] text-zinc-600 font-mono">Round {item.round}</span>
            </div>
            <span className="text-[8px] px-1.5 py-0.5 rounded-full border font-mono font-bold uppercase bg-emerald-500/10 text-emerald-400 border-emerald-500/25">
              {Math.round(item.confidence * 100)}% conf
            </span>
          </div>
          <ContentBlocks blocks={item.contentBlocks} />
        </>
      ) : (
        <>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-rose-400">{name(item.sender)}</span>
              <span className="text-[9px] text-zinc-600 font-mono">
                → {name(item.target)} · Round {item.round}
              </span>
            </div>
            <span
              className={`text-[8px] px-1.5 py-0.5 rounded-full border font-mono font-bold uppercase ${SEVERITY_STYLE[item.severity]}`}
            >
              {item.severity}
            </span>
          </div>
          <p className="text-[11.5px] leading-relaxed text-zinc-300 font-sans tracking-wide whitespace-pre-wrap">
            {item.content}
          </p>
        </>
      )}
    </motion.div>
  );
}
