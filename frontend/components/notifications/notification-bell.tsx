"use client";

/**
 * Header notification bell + dropdown pane — ported from the reference `App.tsx`
 * "global notification action center". Shows an unread badge, and a dropdown
 * "Event Log Matrix" with the swarm chronology plus toggles for the auto-
 * simulation stream and the floating toast overlays. Opening it marks all read.
 * Backed entirely by {@link useNotifications}.
 */
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell } from "lucide-react";
import { useNotifications, type AlertStatus } from "@/features/notifications/use-notifications";

const STATUS_DOT: Record<AlertStatus, string> = {
  completes: "bg-[#10b981]",
  critique: "bg-orange-500",
  error: "bg-rose-500",
  warning: "bg-amber-500",
  sync: "bg-sky-400",
};

export function NotificationBell() {
  const {
    toasts,
    unreadCount,
    simActive,
    showFloatingOverlays,
    markAllAsRead,
    clearAll,
    setSimActive,
    setShowFloatingOverlays,
  } = useNotifications();
  const [open, setOpen] = useState(false);
  const paneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (paneRef.current && !paneRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const toggle = () => {
    setOpen((v) => !v);
    if (!open) markAllAsRead();
  };

  return (
    <div className="relative" ref={paneRef}>
      <button
        type="button"
        onClick={toggle}
        title="System event notifications"
        className={`relative p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-center ${
          open
            ? "bg-[#10b981]/10 border-[#10b981]/30 text-emerald-400"
            : unreadCount > 0
              ? "border-[#10b981]/20 text-white hover:border-[#10b981]/40 bg-[#050506]"
              : "border-white/10 text-zinc-400 hover:text-white hover:bg-white/5"
        }`}
      >
        <Bell className={`w-4 h-4 ${unreadCount > 0 ? "animate-bounce" : ""}`} />
        {unreadCount > 0 ? (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-500 text-black font-black text-[9px] flex items-center justify-center border-2 border-[#050506] select-none">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        ) : null}
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: 15, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 15, scale: 0.95 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="absolute right-0 top-full mt-3 w-96 max-w-[calc(100vw-2rem)] bg-[#090e0b]/95 backdrop-blur-2xl border border-white/15 rounded-xl p-4 shadow-[0_15px_50px_rgba(0,0,0,0.9)] z-[65]"
          >
            <div className="flex items-center justify-between pb-3 border-b border-white/15 mb-3">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                  Event Log Matrix
                </h4>
                <p className="text-[9px] text-zinc-500 font-mono tracking-tight">
                  AUTONOMOUS SWARM CHRONOLOGY
                </p>
              </div>
              {toasts.length > 0 ? (
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-zinc-500 hover:text-zinc-300 font-mono text-[9px] uppercase tracking-wider cursor-pointer"
                >
                  Clear All
                </button>
              ) : null}
            </div>

            <div className="p-2.5 bg-[#0c0c0e] border border-white/5 rounded-lg mb-3 space-y-2">
              <ToggleRow
                label="Auto-Simulation Stream:"
                active={simActive}
                onToggle={() => setSimActive(!simActive)}
                onLabel="STREAMING"
                offLabel="MUTED"
              />
              <ToggleRow
                label="Allow Temporary Toast Overlays:"
                active={showFloatingOverlays}
                onToggle={() => setShowFloatingOverlays(!showFloatingOverlays)}
                onLabel="SHOWING"
                offLabel="MUTED (LOG ONLY)"
              />
            </div>

            {toasts.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                  No recent system integrations logged
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {toasts.map((toast) => (
                  <div
                    key={toast.id}
                    className="p-2 bg-black/40 border border-white/5 rounded-lg text-xs hover:border-white/10 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[toast.status]}`} />
                        <span className="font-sans font-bold text-white uppercase text-[9.5px] truncate">
                          {toast.agent}
                        </span>
                      </div>
                      <span className="text-[8.5px] font-mono text-zinc-500 shrink-0">{toast.time}</span>
                    </div>
                    <p className="text-zinc-400 text-[10px] mt-1 leading-snug">{toast.action}</p>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function ToggleRow({
  label,
  active,
  onToggle,
  onLabel,
  offLabel,
}: {
  label: string;
  active: boolean;
  onToggle: () => void;
  onLabel: string;
  offLabel: string;
}) {
  return (
    <div className="flex items-center justify-between text-[10px]">
      <span className="text-zinc-400 font-medium">{label}</span>
      <button
        type="button"
        onClick={onToggle}
        className={`px-2 py-0.5 rounded text-[8.5px] font-mono font-bold tracking-widest border transition-all cursor-pointer ${
          active
            ? "bg-emerald-500/10 border-emerald-500/35 text-emerald-400"
            : "bg-zinc-900 border-white/5 text-zinc-500"
        }`}
      >
        {active ? onLabel : offLabel}
      </button>
    </div>
  );
}
