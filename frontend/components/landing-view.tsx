"use client";

/**
 * Landing page (Bug 1) — ported from the reference `src/views/LandingView.tsx`
 * visual language (3-column hero, capabilities grid, stats row, CTA) using
 * `framer-motion` + the shared `artistic-*` classes already in globals.css.
 *
 * The reference's live debate simulation (AgentGraph / DebateThread driven by
 * simulationTemplates) is intentionally NOT reproduced here: that engine belongs
 * to the Session Workspace and would require the AG-UI mock replayer. A static
 * "telemetry" panel preserves the layout. Every CTA calls `login()` — clicking
 * any of them logs the user in and reveals the dashboard, matching the reference
 * where `onStartSession` / `onNavigateToWorkspace` all routed through `handleLogin`.
 */
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/features/auth/use-auth";

const CAPABILITIES: readonly { icon: string; title: string; desc: string }[] = [
  {
    icon: "⬡",
    title: "Agent mesh graph",
    desc: "Interactive node map where connections only highlight when a message flows. No mock lines, absolute accuracy.",
  },
  {
    icon: "⊶",
    title: "PR-style debate panel",
    desc: "Every CRITIQUE, ENDORSE, and VOTE rendered as code-review lines. Follow conflicts and resolutions objectively.",
  },
  {
    icon: "◎",
    title: "Consensus ring",
    desc: "Telemetry on multi-agent alignment. Watch percentages rise as specialist agents negotiate standards.",
  },
  {
    icon: "⌬",
    title: "Lifecycle-driven layout",
    desc: "Adapts to the task phase: output occupies center-stage at synthesis, collapsing when agent debate resumes.",
  },
  {
    icon: "⟐",
    title: "Blackboard + scrubber",
    desc: "Shared memory space with round-by-round time scrubbers. Replay agent messages and track mutations.",
  },
  {
    icon: "⊛",
    title: "Inference profiles",
    desc: "Adjust temperature, top-P, and reasoning parameters per role. Override model limits at specific junctions.",
  },
];

const STATS: readonly { num: string; desc: string }[] = [
  { num: "N²", desc: "Fully connected agent mesh topology config" },
  { num: "τ", desc: "Configurable consensus threshold per session" },
  { num: "5+", desc: "LLMs supported: Gemini, Claude, GPT, Ollama" },
  { num: "AG-UI", desc: "Contract-first atomic real-time protocol" },
];

export function LandingView() {
  const { login } = useAuth();

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      className="relative flex flex-col items-center overflow-x-hidden w-full"
    >
      {/* The animated agent-mesh backdrop is now the global ThreeMeshBackground
          (mounted in app/layout.tsx) and spans every route, including this one. */}

      {/* 3-COLUMN HERO */}
      <section className="w-full max-w-7xl xl:max-w-[1550px] mt-8 md:mt-16 mb-20 px-6 md:px-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch relative z-10 text-stone-300">
        {/* LEFT RAIL */}
        <aside className="hidden lg:flex lg:col-span-1 flex-col items-center justify-between py-8 border-r border-white/10 pr-6">
          <div className="w-8 h-8 bg-white rounded flex items-center justify-center text-black font-mono font-black text-[11px] shadow-[0_0_15px_rgba(255,255,255,0.2)]">
            Nx
          </div>
          <div className="text-[9px] font-mono tracking-[0.45em] text-zinc-500 uppercase select-none [writing-mode:vertical-rl]">
            CONVERGENCE_ENGINE
          </div>
          <div className="text-zinc-600 text-[10.5px] font-mono font-bold">©26</div>
        </aside>

        {/* MIDDLE: hero + CTAs */}
        <div className="col-span-12 lg:col-span-8 flex flex-col justify-center text-left lg:pr-10 py-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15 }}
            className="inline-flex items-center gap-2 border border-white/10 bg-white/5 text-neutral-300 text-[10px] tracking-[0.2em] font-semibold px-4 py-2 rounded-full mb-6 w-fit uppercase"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse inline-block" />
            <span>Multi-Agent Operating System</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-sans font-black tracking-tight leading-[1.05] mb-6 text-white"
          >
            {/* Infinite color-swap: parts A & C and part B alternate White <-> Emerald
                simultaneously (5s easeInOut loop), with an emerald drop-shadow glow that
                fades in/out in step with the green phase. Each segment is inline-block so
                its color/filter animate independently. */}
            <motion.span
              className="inline-block font-black"
              animate={{
                color: ["#ffffff", "#10b981", "#ffffff"],
                filter: [
                  "drop-shadow(0 0px 0px rgba(0,0,0,0))",
                  "drop-shadow(0 2px 10px rgba(16,185,129,0.25))",
                  "drop-shadow(0 0px 0px rgba(0,0,0,0))",
                ],
              }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
            >
              Your autonomous
            </motion.span>{" "}
            <br />
            <motion.span
              className="inline-block font-black"
              animate={{
                color: ["#10b981", "#ffffff", "#10b981"],
                filter: [
                  "drop-shadow(0 2px 10px rgba(16,185,129,0.25))",
                  "drop-shadow(0 0px 0px rgba(0,0,0,0))",
                  "drop-shadow(0 2px 10px rgba(16,185,129,0.25))",
                ],
              }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
            >
              engineering team,
            </motion.span>{" "}
            <br />
            <motion.span
              className="inline-block font-black"
              animate={{
                color: ["#ffffff", "#10b981", "#ffffff"],
                filter: [
                  "drop-shadow(0 0px 0px rgba(0,0,0,0))",
                  "drop-shadow(0 2px 10px rgba(16,185,129,0.25))",
                  "drop-shadow(0 0px 0px rgba(0,0,0,0))",
                ],
              }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
            >
              converging in real time
            </motion.span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="text-zinc-400 text-sm md:text-base max-w-xl leading-relaxed mb-8 font-sans font-normal"
          >
            NEX AGI orchestrates specialist AI agents that debate, critique, and synthesise — so complex
            software goals don&apos;t just get answered, they get solved.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="flex flex-wrap items-center gap-4"
          >
            <button
              type="button"
              onClick={login}
              className="px-6 py-3.5 bg-white hover:bg-zinc-200 text-black font-extrabold text-[11px] tracking-widest uppercase rounded shadow-[0_4px_24px_rgba(255,255,255,0.15)] transition-all cursor-pointer hover:scale-[1.01] active:scale-95 flex items-center gap-2"
            >
              <span>Initialize Node</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={login}
              className="px-6 py-3.5 bg-transparent border border-white/20 hover:border-white/50 hover:bg-white/5 text-white font-extrabold text-[11px] tracking-widest uppercase rounded transition-all cursor-pointer active:scale-95"
            >
              <span>Watch live run</span>
            </button>
          </motion.div>
        </div>

        {/* RIGHT: metrics pane */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col justify-between p-7 rounded-2xl artistic-pane">
          <div className="space-y-6">
            <div className="border-b border-white/10 pb-4">
              <div className="text-[9.5px] font-bold uppercase tracking-[0.2em] text-zinc-500 mb-1">
                CONVERGENCE SPEED
              </div>
              <div className="text-3xl font-mono text-white font-extrabold flex items-baseline gap-1">
                94.8<span className="text-xs text-[#10b981] font-sans font-bold">% Rate</span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono mt-1 leading-normal">
                Successful blueprint convergence reached across heterogenous mesh nodes.
              </p>
            </div>
            <div className="border-b border-white/10 pb-4">
              <div className="text-[9.5px] font-bold uppercase tracking-[0.2em] text-zinc-500 mb-1">
                DECISION INTERVAL
              </div>
              <div className="text-3xl font-mono text-white font-extrabold flex items-baseline gap-1">
                1.8<span className="text-xs text-[#10b981] font-sans font-bold">s Average</span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono mt-1 leading-normal">
                Average debate round validation and next-token consensus updates.
              </p>
            </div>
            <div>
              <div className="text-[9.5px] font-bold uppercase tracking-[0.2em] text-zinc-500 mb-2">
                SYNTHESIS QUALITY
              </div>
              <div className="text-3xl font-mono text-white font-extrabold">A+ Grade</div>
              <p className="text-[10px] text-zinc-500 font-mono mt-1 leading-normal">
                Strict type safety, edge-case coverage and robust caching profiles.
              </p>
              <div className="mt-3.5 h-[3px] bg-white/10 rounded-full overflow-hidden">
                <div className="w-[94.8%] h-full bg-[#10b981] rounded-full transition-all duration-1000" />
              </div>
            </div>
          </div>
        </aside>
      </section>

      {/* CAPABILITIES */}
      <section className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-24 relative z-10 text-stone-300">
        <div className="mb-14">
          <p className="text-zinc-500 text-[10px] font-mono font-bold tracking-[0.3em] uppercase mb-2">
            SYSTEM SPECS &amp; LAYERS
          </p>
          <h2 className="text-3xl md:text-5xl font-extrabold text-white tracking-tight mb-4">
            Not a chat. An OS.
          </h2>
          <p className="text-zinc-400 text-sm md:text-base max-w-xl leading-relaxed">
            NEX AGI gives you a real-time view into how agents reason, debate, and converge — every
            interaction grounded in a real, trackable system coordinate.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {CAPABILITIES.map((item, index) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 15 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.05 }}
              className="p-6 rounded-2xl artistic-pane artistic-pane-hover group cursor-default"
            >
              <div className="w-10 h-10 rounded bg-white/5 border border-white/15 text-white font-mono text-sm flex items-center justify-center mb-4 group-hover:bg-white/10 group-hover:border-white/30 transition-all">
                {item.icon}
              </div>
              <h4 className="text-white font-extrabold text-sm mb-2 group-hover:text-[#a3a3a3] transition-colors">
                {item.title}
              </h4>
              <p className="text-zinc-400 text-xs leading-relaxed">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* STATS */}
      <section className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-24 relative z-10">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 artistic-pane rounded-2xl p-6 divide-y lg:divide-y-0 lg:divide-x divide-white/10">
          {STATS.map((stat) => (
            <div key={stat.num} className="p-4 flex flex-col justify-center text-center lg:text-left">
              <h3 className="text-3xl md:text-4xl font-mono font-black text-white mb-2">
                {stat.num === "τ" ? (
                  <span className="text-white italic">τ</span>
                ) : (
                  <>
                    {stat.num.slice(0, -1)}
                    <span className="text-zinc-400 font-mono font-medium">{stat.num.slice(-1)}</span>
                  </>
                )}
              </h3>
              <p className="text-zinc-500 text-xs tracking-wide leading-relaxed font-mono">{stat.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* BOTTOM CTA */}
      <section className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-20 text-center relative z-10">
        <div className="relative artistic-pane rounded-3xl p-10 md:p-14 overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.4)]">
          <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-3 tracking-tight">
            Run your first multi-agent session
          </h2>
          <p className="text-zinc-400 text-xs md:text-sm max-w-lg mx-auto mb-8 leading-relaxed">
            Set an ambitious engineering goal. Deploy your specialist agent mesh. Watch the debate, track
            consensus, and ship the synthesized files.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              type="button"
              onClick={login}
              className="w-full sm:w-auto px-6 py-3 bg-white hover:bg-zinc-200 text-black font-extrabold rounded text-xs sm:text-sm tracking-wider uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-[0_4px_24px_rgba(255,255,255,0.15)]"
            >
              <span>Initialize uplink</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={login}
              className="w-full sm:w-auto px-6 py-3 bg-transparent border border-white/20 hover:border-white/40 hover:bg-white/5 text-white font-bold rounded text-xs sm:text-sm tracking-wide uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <span>Manage Models</span>
            </button>
          </div>
        </div>
      </section>
    </motion.div>
  );
}
