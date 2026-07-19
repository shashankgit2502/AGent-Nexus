"use client";

/**
 * Notifications provider — the global "swarm event bus" ported from the reference
 * `App.tsx` notification system (Bugs 4 & 5). It is the single source of truth for:
 *
 *  - the in-memory `toasts` log (newest first, capped at 32),
 *  - the unread badge count for the header bell,
 *  - the floating-overlay + auto-simulation toggles,
 *  - a background simulation that emits a random agent event every 11s, and
 *  - a window `nexagi-new-alert` CustomEvent seam so any surface (the dashboard
 *    Event Bus Matrix, future real AG-UI events) can inject an alert by
 *    dispatching, without importing this module.
 *
 * Reference parity: `notify()` ⇄ the reference `triggerToast`; the
 * `nexagi-new-alert` listener and 11s interval mirror the reference exactly. The
 * dashboard simulator card and the header bell both read/write this one store, so
 * a click, an auto-generated tick, and the journal/overlay/bell all stay in sync.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

// `warning` = a fixable, non-fatal condition (e.g. an agent abstaining because its
// model can't call tools, §9.3) — amber, distinct from the red `error` for a hard
// failure, so a config issue doesn't read as a crash.
export type AlertStatus = "completes" | "critique" | "error" | "sync" | "warning";

export interface ToastAlert {
  id: string;
  agent: string;
  action: string;
  status: AlertStatus;
  time: string;
  read: boolean;
}

/** Detail payload for the `nexagi-new-alert` window CustomEvent seam. */
export interface NewAlertDetail {
  agent: string;
  action: string;
  status: AlertStatus;
}

export const NEW_ALERT_EVENT = "nexagi-new-alert";

/** Dispatch helper so callers don't hand-build the CustomEvent. */
export function emitAlert(detail: NewAlertDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<NewAlertDetail>(NEW_ALERT_EVENT, { detail }));
}

const MAX_TOASTS = 32;
const SIM_INTERVAL_MS = 11_000;

const SIMULATED_AGENT_UPDATES: readonly NewAlertDetail[] = [
  { agent: "Creative Architect", action: "Drafted modular Redis clustering blueprint", status: "completes" },
  { agent: "Strict Auditor", action: "Identified single-point-of-failure in master consensus path v2", status: "critique" },
  { agent: "Pedantic QA Tester", action: "Completed automated stress injection on rate-limit queues", status: "completes" },
  { agent: "Zero-Latency DevOps", action: "Compiled build deliverables for isolated Docker container", status: "sync" },
  { agent: "NEX AGI Co-ordinator", action: "Convergence rating raised to 94.8% after multi-round debate", status: "completes" },
  { agent: "Knowledge Vector Hub", action: "Optimized 1536-dim spatial indexes across pgvector cluster", status: "sync" },
  { agent: "Security Monitor", action: "Prevented anomalous thread concurrency leak from test harness", status: "error" },
];

function timeLabel(): string {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface NotificationsContextValue {
  toasts: ToastAlert[];
  unreadCount: number;
  simActive: boolean;
  showFloatingOverlays: boolean;
  notify: (agent: string, action: string, status: AlertStatus) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
  dismiss: (id: string) => void;
  setSimActive: (next: boolean) => void;
  setShowFloatingOverlays: (next: boolean) => void;
}

const NotificationsContext = createContext<NotificationsContextValue | null>(null);

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastAlert[]>([
    {
      id: "t-init",
      agent: "Orchestrating Router",
      action: "Active cognition session started successfully",
      status: "completes",
      time: "12:45 PM",
      read: true,
    },
  ]);
  const [simActive, setSimActive] = useState(true);
  const [showFloatingOverlays, setShowFloatingOverlays] = useState(false);

  // `notify` is referenced by the window listener + interval; keep it stable so
  // those effects don't re-subscribe on every toast change.
  const notify = useCallback((agent: string, action: string, status: AlertStatus) => {
    const alert: ToastAlert = {
      id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      agent,
      action,
      status,
      time: timeLabel(),
      read: false,
    };
    setToasts((prev) => [alert, ...prev].slice(0, MAX_TOASTS));
  }, []);

  // Window event seam: any surface can inject an alert by dispatching
  // `nexagi-new-alert` (exact reference behaviour).
  useEffect(() => {
    const handle = (event: Event) => {
      const detail = (event as CustomEvent<NewAlertDetail>).detail;
      if (detail) notify(detail.agent, detail.action, detail.status);
    };
    window.addEventListener(NEW_ALERT_EVENT, handle);
    return () => window.removeEventListener(NEW_ALERT_EVENT, handle);
  }, [notify]);

  // Background swarm simulation — a gentle event every 11s while streaming is on.
  const tickRef = useRef(0);
  useEffect(() => {
    if (!simActive) return;
    const interval = window.setInterval(() => {
      const update =
        SIMULATED_AGENT_UPDATES[tickRef.current % SIMULATED_AGENT_UPDATES.length];
      tickRef.current += 1;
      if (update) notify(update.agent, update.action, update.status);
    }, SIM_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [simActive, notify]);

  const markAllAsRead = useCallback(() => {
    setToasts((prev) => prev.map((t) => (t.read ? t : { ...t, read: true })));
  }, []);
  const clearAll = useCallback(() => setToasts([]), []);
  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const value = useMemo<NotificationsContextValue>(() => {
    const unreadCount = toasts.reduce((n, t) => (t.read ? n : n + 1), 0);
    return {
      toasts,
      unreadCount,
      simActive,
      showFloatingOverlays,
      notify,
      markAllAsRead,
      clearAll,
      dismiss,
      setSimActive,
      setShowFloatingOverlays,
    };
  }, [toasts, simActive, showFloatingOverlays, notify, markAllAsRead, clearAll, dismiss]);

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

export function useNotifications(): NotificationsContextValue {
  const ctx = useContext(NotificationsContext);
  if (!ctx) {
    throw new Error("useNotifications must be used within a NotificationsProvider");
  }
  return ctx;
}
