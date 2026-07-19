"use client";

/**
 * Dashboard information cards — ported from the reference `DashboardView` bento
 * panels into the live frontend (FRONTEND_SPEC dashboard surface).
 *
 * Three self-contained panels sit below the real `/stats` tiles on the home page:
 *  - {@link BackendAdviserCard}: interactive backend/storage strategy advisor.
 *  - {@link MeshHealthCard}: host telemetry + latest-logs readout.
 *  - {@link NotificationSimulatorCard}: a local event-bus simulator with a journal.
 *
 * These reproduce the reference's "good frontend in the cards" verbatim in look,
 * retyped for `strict` TS and the frontend's `framer-motion` import (the reference
 * used `motion/react`). They are presentational/illustrative — no backend calls —
 * so the dashboard reads as a populated control room even before live telemetry is
 * wired. The reference reached for stray Tailwind shades that don't exist in this
 * config (`emerald-550`, `zinc-650`, `zinc-805`, …); those are mapped to real
 * scale steps here so the build stays clean.
 */
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bell,
  Database,
  Pause,
  Server,
  Trash2,
  Wifi,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useNotifications, type AlertStatus } from "@/features/notifications/use-notifications";

type BackendId = "fastapi" | "node" | "firebase";

interface BackendOption {
  id: BackendId;
  name: string;
  desc: string;
  icon: LucideIcon;
}

const BACKEND_OPTIONS: readonly BackendOption[] = [
  { id: "fastapi", name: "Python FastAPI", desc: "Best for RAG & AI", icon: Server },
  { id: "node", name: "Node.js Express", desc: "Unified JS Stack", icon: Zap },
  { id: "firebase", name: "Google Firebase", desc: "Serverless Realtime", icon: Database },
];

interface BackendDetail {
  badge: string;
  badgeTone: string;
  title: string;
  body: string;
  left: { label: string; value: string };
  right: { label: string; value: string };
}

const BACKEND_DETAILS: Record<BackendId, BackendDetail> = {
  fastapi: {
    badge: "RECOMMENDED FOR AGENTS",
    badgeTone: "bg-[#10b981]/10 text-[#10b981]",
    title: "✓ OPTION A: Python + FastAPI + PostgreSQL (pgvector)",
    body: "This stack is superior for agentic platforms. LangChain, LangGraph, and native embedding drivers compile fastest here. pgvector handles structural cognitive memory vectors natively.",
    left: { label: "Primary Database:", value: "PostgreSQL with pgvector extension" },
    right: { label: "Embedding Engine:", value: "OpenAI text-embedding-3 or Gemini Embed" },
  },
  node: {
    badge: "HIGH SPEED",
    badgeTone: "bg-zinc-800 text-zinc-400",
    title: "✓ OPTION B: Node.js + Express + Drizzle / Prisma Schema",
    body: "Ideal when sharing models/validators between your frontend SPA and server backend. Runs beautifully inside serverless edge containers and uses WebSocket connections for seamless real-time stream reductions.",
    left: { label: "ORM Integration:", value: "Drizzle / Prisma TypeScript schema" },
    right: { label: "WebSocket Transport:", value: "WebSockets coupled with Node EventEmitters" },
  },
  firebase: {
    badge: "ZERO INFRASTRUCTURE",
    badgeTone: "bg-zinc-800 text-zinc-400",
    title: "✓ OPTION C: Serverless Firestore Database + Firebase Auth",
    body: "Provides built-in document sync directly to the browser with security listeners. No server state setup or Express routing required for general CRUD state stores.",
    left: { label: "Database Engine:", value: "Durable Cloud Google Firestore" },
    right: { label: "Security Layers:", value: "Built-in declarative Firestore rules" },
  },
};

const STATUS_DOT: Record<AlertStatus, string> = {
  completes: "bg-[#10b981]",
  critique: "bg-orange-500",
  error: "bg-rose-500",
  warning: "bg-amber-500",
  sync: "bg-sky-400",
};

export function DashboardCards() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <BackendAdviserCard />
        <MeshHealthCard />
      </div>
      <NotificationSimulatorCard />
    </div>
  );
}

function BackendAdviserCard() {
  const [selected, setSelected] = useState<BackendId>("fastapi");
  const detail = BACKEND_DETAILS[selected];

  return (
    <section className="lg:col-span-8 p-6 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[8.5px] rounded font-mono font-bold tracking-wider uppercase">
            Architectural Design
          </span>
          <span className="text-zinc-600 font-mono text-xs">•</span>
          <p className="text-[10px] font-mono tracking-widest text-zinc-400 uppercase">
            Interactive Backend Adviser
          </p>
        </div>
        <h3 className="text-lg font-bold text-white mb-4">
          Select the Ideal Backend &amp; Storage Strategy
        </h3>

        <p className="text-zinc-400 text-xs leading-relaxed mb-6">
          NEX AGI uses a multi-agent state machine. To build a production-ready application, select
          the backend configuration that best fits your scale, real-time sync needs, and memory
          database constraints.
        </p>

        <div className="grid grid-cols-3 gap-2 mb-6">
          {BACKEND_OPTIONS.map((option) => {
            const Icon = option.icon;
            const active = selected === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => setSelected(option.id)}
                className={`p-3.5 rounded-xl border text-left transition-all ${
                  active
                    ? "bg-emerald-500/10 border-[#10b981] text-white"
                    : "bg-white/[0.02] border-white/5 text-zinc-400 hover:border-white/10 hover:bg-white/[0.04]"
                }`}
              >
                <Icon className={`w-4 h-4 mb-1.5 ${active ? "text-[#10b981]" : "text-zinc-400"}`} />
                <p className="font-bold text-[11px] leading-tight tracking-wider uppercase">
                  {option.name}
                </p>
                <p className="text-[9px] text-zinc-500 mt-0.5">{option.desc}</p>
              </button>
            );
          })}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={selected}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-4 bg-white/[0.02] border border-white/5 rounded-xl p-4 text-xs font-mono"
          >
            <div className="flex items-center justify-between text-[11px] text-[#10b981] gap-2">
              <span className="font-bold">{detail.title}</span>
              <span
                className={`px-2 py-0.5 text-[9px] rounded font-bold shrink-0 ${detail.badgeTone}`}
              >
                {detail.badge}
              </span>
            </div>
            <p className="text-zinc-400 text-[11px] leading-relaxed">{detail.body}</p>
            <div className="grid grid-cols-2 gap-4 text-[10px] text-zinc-500 pt-1">
              <div>
                <span className="block font-black text-zinc-400">{detail.left.label}</span>
                {detail.left.value}
              </div>
              <div>
                <span className="block font-black text-zinc-400">{detail.right.label}</span>
                {detail.right.value}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="text-[10px] text-zinc-500 border-t border-white/5 pt-4 mt-6 flex items-center justify-between gap-3">
        <span>Enterprise-grade RAG vectors: pgvector or Pinecone.</span>
        <span className="font-semibold text-emerald-400 hover:underline cursor-pointer">
          Learn details in System Blueprint Docs
        </span>
      </div>
    </section>
  );
}

const HEALTH_BARS: readonly { label: string; value: string; width: string; tone: string }[] = [
  { label: "Consensus Intensity", value: "96% Status", width: "96%", tone: "bg-emerald-500" },
  { label: "Vector Index Sync", value: "100% Synced", width: "100%", tone: "bg-[#10b981]" },
  { label: "Thread Concurrency", value: "8/12 Threads", width: "66%", tone: "bg-teal-400" },
];

const LATEST_LOGS: readonly { log: string; time: string }[] = [
  { log: "Conducted round 5 validation on Rate-Limiter", time: "11:24" },
  { log: "Cached 28 cognitive memory facts to pgvector", time: "11:15" },
  { log: 'Assigned "Pedantic critique" behavior style to QA', time: "11:02" },
];

function MeshHealthCard() {
  return (
    <section className="lg:col-span-4 p-6 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between">
      <div className="space-y-5">
        <div>
          <p className="text-[9.5px] font-mono tracking-widest text-zinc-500 uppercase">
            System Health
          </p>
          <h4 className="text-sm font-bold text-white mt-1">Autonomous Host Telemetry</h4>
        </div>

        <div className="space-y-3.5">
          {HEALTH_BARS.map((bar) => (
            <div key={bar.label}>
              <div className="flex justify-between text-[10px] font-mono text-zinc-400 mb-1">
                <span className="uppercase">{bar.label}</span>
                <span className="text-white">{bar.value}</span>
              </div>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div className={`h-full ${bar.tone} rounded-full`} style={{ width: bar.width }} />
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-2 border-t border-white/5 pt-3">
          <p className="text-[9px] font-mono text-zinc-500 tracking-wider">LATEST LOGS</p>
          {LATEST_LOGS.map((item) => (
            <div
              key={item.log}
              className="flex justify-between gap-2.5 text-[9.5px] font-mono text-zinc-400"
            >
              <span className="truncate">▶ {item.log}</span>
              <span className="text-zinc-600 shrink-0">{item.time}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 pt-4 border-t border-white/5 bg-white/[0.01] p-3 rounded-lg text-[10px] leading-relaxed text-zinc-400 font-mono">
        <strong>System summary:</strong> Your multi-agent swarm has processed all active consensus
        routines and generated stable builds.
      </div>
    </section>
  );
}

interface TriggerSpec {
  label: string;
  action: string;
  status: AlertStatus;
  desc: string;
  color: string;
}

const TRIGGERS: readonly TriggerSpec[] = [
  {
    label: "Creative Architect",
    action: "Approved React styling layer guidelines",
    status: "completes",
    desc: "Notify completion",
    color: "border-emerald-500/45 hover:bg-emerald-500/5 hover:border-emerald-400",
  },
  {
    label: "Strict Auditor",
    action: "Detected unhandled state recursion trace in thread Q",
    status: "critique",
    desc: "Notify warning",
    color: "border-rose-500/45 hover:bg-rose-500/5 hover:border-rose-400",
  },
  {
    label: "Pedantic QA Tester",
    action: "Injected 50 concurrent client mocks without latency loss",
    status: "completes",
    desc: "Notify test metrics",
    color: "border-teal-500/45 hover:bg-teal-500/5 hover:border-teal-400",
  },
  {
    label: "Zero-Latency DevOps",
    action: "Refreshed pgvector connection pool",
    status: "sync",
    desc: "Notify sync event",
    color: "border-sky-500/45 hover:bg-sky-500/5 hover:border-sky-400",
  },
];

function NotificationSimulatorCard() {
  // Backed by the global notification bus: clicks and the auto-generate stream
  // feed the same store that drives the header bell and floating overlay, so the
  // journal here stays in lock-step with the rest of the app (Bugs 4 & 5).
  const { toasts, simActive, setSimActive, clearAll, notify } = useNotifications();

  const pushToast = (trigger: TriggerSpec) => {
    notify(trigger.label, trigger.action, trigger.status);
  };

  return (
    <section className="p-6 rounded-2xl bg-[#09090b]/80 border border-white/10 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-white/10 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <p className="text-[10px] font-mono tracking-[0.2em] text-[#10b981] uppercase font-bold">
              Event Bus Matrix
            </p>
          </div>
          <h3 className="text-base font-bold text-white mt-1">
            Real-Time Swarm Notification Simulator
          </h3>
          <p className="text-zinc-500 text-[11px] font-medium">
            Click any telemetry node below to inject a real-time state-machine reduction into the
            alert journal.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-zinc-400 uppercase">Auto-Generate:</span>
          <button
            type="button"
            onClick={() => setSimActive(!simActive)}
            className={`px-3 py-1.5 rounded-lg text-[9.5px] font-mono font-bold uppercase border tracking-wider transition-all flex items-center gap-1.5 cursor-pointer ${
              simActive
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-zinc-900 border-white/5 text-zinc-500 hover:text-zinc-400"
            }`}
          >
            {simActive ? (
              <Wifi className="w-3.5 h-3.5 animate-pulse text-emerald-400" />
            ) : (
              <Pause className="w-3.5 h-3.5" />
            )}
            <span>{simActive ? "Streaming Active" : "Stream Muted"}</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {TRIGGERS.map((trigger) => (
          <button
            key={trigger.label}
            type="button"
            onClick={() => pushToast(trigger)}
            className={`p-3.5 rounded-xl border text-left bg-black/40 transition-all cursor-pointer flex flex-col justify-between h-24 ${trigger.color}`}
          >
            <div className="flex items-center justify-between w-full">
              <span className="text-[10px] font-sans font-black text-white uppercase tracking-wider">
                {trigger.label}
              </span>
              <Zap className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
            </div>
            <div className="mt-2 text-left">
              <p className="text-[10.5px] text-zinc-300 leading-snug line-clamp-1 font-medium">
                {trigger.action}
              </p>
              <p className="text-[8.5px] text-zinc-500 font-mono mt-0.5 uppercase tracking-widest">
                {trigger.desc}
              </p>
            </div>
          </button>
        ))}
      </div>

      <div className="bg-[#111113]/30 border border-white/5 rounded-xl p-4">
        <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
          <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest flex items-center gap-1.5">
            <Bell className="w-3.5 h-3.5 text-[#10b981]" />
            Recent Alert Journal ({toasts.length})
          </span>
          {toasts.length > 0 ? (
            <button
              type="button"
              onClick={clearAll}
              className="text-zinc-500 hover:text-white font-mono text-[9px] uppercase tracking-wider flex items-center gap-1 cursor-pointer"
            >
              <Trash2 className="w-3 h-3" /> Clear Journal
            </button>
          ) : null}
        </div>
        {toasts.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-[10.5px] font-mono text-zinc-500 uppercase tracking-wider">
              No active event logs recorded in journal
            </p>
          </div>
        ) : (
          <div className="space-y-2.5 max-h-48 overflow-y-auto pr-2">
            {toasts.map((toast) => (
              <div
                key={toast.id}
                className="flex items-center justify-between p-2.5 bg-[#09090b]/80 border border-white/10 rounded-lg text-xs"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[toast.status]}`} />
                  <span className="font-sans font-bold text-white uppercase tracking-tight text-[10px] w-28 truncate select-none">
                    {toast.agent}
                  </span>
                  <span className="text-zinc-400 font-mono text-[11px] truncate">
                    {toast.action}
                  </span>
                </div>
                <span className="text-[9.5px] font-mono text-zinc-500 ml-4 shrink-0">
                  {toast.time}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
