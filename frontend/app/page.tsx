"use client";

/**
 * Dashboard / landing (Slice 4).
 *
 * Replaces the Slice-1 offline "seam self-test" with live headline counts from
 * `GET /stats` (React Query — the locked home for REST DTOs). The hero keeps the
 * ported reference visual language; the tiles below are real, org-scoped data.
 */
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Users,
  Bot,
  Cpu,
  Activity,
  CheckCircle2,
  MessageSquare,
  Database,
  ArrowUpRight,
} from "lucide-react";
import { useStats } from "@/features/dashboard/use-stats";
import { DashboardCards } from "@/features/dashboard/dashboard-cards";
import { QueryBoundary } from "@/components/crud/primitives";
import type { StatsRead } from "@/types/api";

interface TileSpec {
  key: keyof StatsRead;
  label: string;
  hint: string;
  icon: typeof Users;
  href?: string;
}

const TILES: TileSpec[] = [
  { key: "teams", label: "Teams", hint: "Active", icon: Users, href: "/teams" },
  { key: "agents", label: "Agents", hint: "Configured", icon: Bot, href: "/teams" },
  { key: "sessions", label: "Sessions", hint: "Launched", icon: Cpu, href: "/history" },
  { key: "runs", label: "Runs", hint: "Total", icon: Activity, href: "/history" },
  { key: "completed_runs", label: "Completed", hint: "Converged", icon: CheckCircle2, href: "/history" },
  { key: "conversations", label: "Conversations", hint: "Chat", icon: MessageSquare, href: "/chat" },
  { key: "knowledge_sources", label: "Knowledge", hint: "Sources", icon: Database, href: "/knowledge" },
];

export default function DashboardPage() {
  const stats = useStats();

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto px-6 md:px-12 py-16">
      {/* Hero — the animated agent-mesh backdrop is now the global ThreeMeshBackground. */}
      <div className="relative">
        <div className="relative z-10">
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981] mb-4">
            Decentralized multi-agent OS
          </p>
          <h1 className="text-5xl md:text-6xl font-bold artistic-text-gradient max-w-3xl leading-[1.05]">
            A mesh of peer agents converging on one answer.
          </h1>
          <p className="text-zinc-400 mt-5 max-w-xl text-sm leading-relaxed">
            Configure a team of ReAct agents, launch a collaboration session, and watch them
            reason over a shared blackboard — gated by you before final synthesis.
          </p>
        </div>
      </div>

      <div className="mt-12">
        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-4">
          Workspace at a glance
        </p>
        <QueryBoundary
          isLoading={stats.isLoading}
          error={stats.error}
          data={stats.data}
          emptyMessage="No stats yet."
        >
          {(data) => (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {TILES.map((tile, i) => (
                <StatTile key={tile.key} spec={tile} value={data[tile.key]} index={i} />
              ))}
            </div>
          )}
        </QueryBoundary>
      </div>

      {/* Ported reference control-room cards (§2): backend adviser, mesh health,
          notification simulator. Presentational — they sit below the live tiles. */}
      <div className="mt-12">
        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-4">
          Control room
        </p>
        <DashboardCards />
      </div>
    </div>
  );
}

function StatTile({ spec, value, index }: { spec: TileSpec; value: number; index: number }) {
  const Icon = spec.icon;
  const body = (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.35, ease: "easeOut" }}
      className="group relative h-32 overflow-hidden rounded-2xl border border-white/10 bg-[#09090b]/80 px-5 py-4 flex flex-col justify-between transition-all hover:border-[#10b981]/40 hover:bg-[#0b0f0d]/80"
    >
      {/* Oversized watermark icon (reference bento language). */}
      <Icon className="pointer-events-none absolute -bottom-4 -right-3 w-24 h-24 stroke-[1.25] text-white/[0.04] group-hover:text-[#10b981]/10 transition-colors" />

      <div className="flex items-center justify-between">
        <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-[#10b981]/10 border border-[#10b981]/20 text-[#10b981]">
          <Icon className="w-4 h-4" />
        </span>
        <span className="text-[8.5px] font-mono uppercase tracking-[0.18em] text-zinc-500 group-hover:text-emerald-400/70 transition-colors">
          {spec.hint}
        </span>
      </div>

      <div className="relative">
        <p className="text-3xl font-black text-white tabular-nums leading-none">{value}</p>
        <div className="mt-1.5 flex items-center justify-between">
          <p className="text-[10px] font-mono uppercase tracking-widest text-zinc-400">
            {spec.label}
          </p>
          {spec.href ? (
            <ArrowUpRight className="w-3.5 h-3.5 text-zinc-600 group-hover:text-emerald-400 transition-colors" />
          ) : null}
        </div>
      </div>
    </motion.div>
  );
  return spec.href ? (
    <Link href={spec.href} className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40 rounded-2xl">
      {body}
    </Link>
  ) : (
    body
  );
}
