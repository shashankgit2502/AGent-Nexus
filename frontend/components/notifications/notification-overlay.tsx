"use client";

/**
 * Floating toast overlay — the bottom-right banner stack ported verbatim from the
 * reference `App.tsx` "dynamic floating toast portal". Shows the four most recent
 * alerts as dismissible neon-accented cards, gated by the `showFloatingOverlays`
 * toggle (off by default — enabled from the header notification pane). Reads its
 * data from {@link useNotifications}; purely presentational.
 */
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useNotifications, type AlertStatus } from "@/features/notifications/use-notifications";

const ACCENT: Record<AlertStatus, { bar: string; border: string; bg: string; dot: string }> = {
  completes: {
    bar: "bg-[#10b981]",
    border: "border-[#10b981]/30",
    bg: "bg-[#050506]/95",
    dot: "bg-emerald-400 shadow-[0_0_8px_#10b981]",
  },
  critique: {
    bar: "bg-orange-500",
    border: "border-orange-500/30",
    bg: "bg-[#0a0602]/95",
    dot: "bg-orange-400 shadow-[0_0_8px_#f97316]",
  },
  error: {
    bar: "bg-rose-500",
    border: "border-rose-500/30",
    bg: "bg-[#0c0204]/95",
    dot: "bg-rose-500 shadow-[0_0_8px_#ef4444]",
  },
  warning: {
    bar: "bg-amber-500",
    border: "border-amber-500/30",
    bg: "bg-[#0c0802]/95",
    dot: "bg-amber-400 shadow-[0_0_8px_#f59e0b]",
  },
  sync: {
    bar: "bg-sky-400",
    border: "border-sky-500/30",
    bg: "bg-[#020508]/95",
    dot: "bg-sky-400 shadow-[0_0_8px_#38bdf8]",
  },
};

export function NotificationOverlay() {
  const { toasts, showFloatingOverlays, dismiss } = useNotifications();

  return (
    <div className="fixed bottom-6 right-6 z-[55] w-full max-w-sm flex flex-col gap-3 pointer-events-none">
      <AnimatePresence>
        {showFloatingOverlays &&
          toasts.slice(0, 4).map((toast) => {
            const accent = ACCENT[toast.status];
            return (
              <motion.div
                key={toast.id}
                layout
                initial={{ opacity: 0, y: 35, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9, x: 40 }}
                transition={{ type: "spring", stiffness: 350, damping: 26 }}
                className={`pointer-events-auto p-4 rounded-xl border ${accent.border} ${accent.bg} backdrop-blur-2xl shadow-[0_10px_35px_rgba(0,0,0,0.7)] flex items-start gap-3 relative overflow-hidden`}
              >
                <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${accent.bar}`} />
                <div className="pt-1.5 shrink-0">
                  <span className={`w-2 h-2 rounded-full block ${accent.dot}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9.5px] font-sans font-black text-white uppercase tracking-wider truncate">
                      {toast.agent}
                    </span>
                    <span className="text-[8.5px] font-mono text-zinc-500 shrink-0">{toast.time}</span>
                  </div>
                  <p className="text-[10.5px] text-zinc-300 font-medium leading-relaxed mt-1">
                    {toast.action}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => dismiss(toast.id)}
                  className="text-zinc-500 hover:text-white p-0.5 rounded transition-colors shrink-0 cursor-pointer self-start select-none"
                  aria-label="Dismiss alert"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            );
          })}
      </AnimatePresence>
    </div>
  );
}
