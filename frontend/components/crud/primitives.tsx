"use client";

/**
 * Shared CRUD presentational primitives (Slice 4).
 *
 * Six CRUD screens (Teams, Agent Builder, Settings→AI, Knowledge, Memory,
 * History) share the same reference visual language — `artistic-pane` glass,
 * emerald accent, mono uppercase eyebrows. Centralising the styled shells here
 * keeps each screen small and the theme consistent (coding-style: many small
 * files; FRONTEND_INTEGRATION_PLAN §1 — reference theme wins). These hold NO
 * data logic — they are pure layout/controls driven by props.
 */
import type { ReactNode } from "react";
import { Loader2, Plus, Inbox, AlertTriangle, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Page shell ────────────────────────────────────────────────────────────────

interface CrudPageProps {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}

/** Standard CRUD screen frame: eyebrow + gradient title + description + body. */
export function CrudPage({ eyebrow, title, description, action, children }: CrudPageProps) {
  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto px-6 md:px-12 py-12">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981] mb-2">
            {eyebrow}
          </p>
          <h1 className="text-3xl font-bold artistic-text-gradient">{title}</h1>
          <p className="text-sm text-zinc-400 leading-relaxed mt-2 max-w-2xl">{description}</p>
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children}
    </div>
  );
}

/** A glass card panel. */
export function Pane({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("artistic-pane rounded-2xl border border-white/10 p-5", className)}>
      {children}
    </div>
  );
}

export function SectionTitle({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-bold text-zinc-100">{label}</h2>
      {hint ? <p className="text-[11px] text-zinc-500 mt-0.5">{hint}</p> : null}
    </div>
  );
}

// ── Form controls ─────────────────────────────────────────────────────────────

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[9.5px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</span>
      {children}
      {hint ? <span className="text-[10px] text-zinc-600">{hint}</span> : null}
    </label>
  );
}

const CONTROL =
  "w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[12px] text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/40 transition-colors";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(CONTROL, props.className)} />;
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(CONTROL, "min-h-[80px] resize-y", props.className)} />;
}

/**
 * Themed `<select>`. Native selects expose no styleable arrow, so we hide the
 * default with `appearance-none`, draw our own chevron, and use a SOLID dark
 * control bg (the closed box) — the open option list is themed globally in
 * globals.css (`color-scheme: dark` + `option` colours).
 */
export function SelectInput({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        {...props}
        className={cn(
          CONTROL,
          "appearance-none cursor-pointer bg-[#0c0f0e] pr-9 hover:border-white/20",
          className,
        )}
      />
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
    </div>
  );
}

/** A labelled boolean toggle row (capability flags, profile switches). */
export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-emerald-500 mt-0.5"
      />
      <span className="flex flex-col">
        <span className="text-[12px] text-zinc-200">{label}</span>
        {hint ? <span className="text-[10.5px] text-zinc-500">{hint}</span> : null}
      </span>
    </label>
  );
}

// ── Buttons ───────────────────────────────────────────────────────────────────

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  icon?: ReactNode;
}

export function PrimaryButton({ loading, icon, children, className, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[11px] font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        className,
      )}
    >
      {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function GhostButton({ icon, children, className, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-zinc-300 hover:text-white hover:bg-white/5 text-[11px] font-semibold transition-colors disabled:opacity-50",
        className,
      )}
    >
      {icon}
      {children}
    </button>
  );
}

/** A small "+" action button for headers. */
export function AddButton({ children, ...rest }: ButtonProps) {
  return (
    <PrimaryButton icon={<Plus className="w-3.5 h-3.5" />} {...rest}>
      {children}
    </PrimaryButton>
  );
}

// ── Status / state ────────────────────────────────────────────────────────────

const PILL_TONES: Record<string, string> = {
  ready: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10",
  completed: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10",
  running: "text-sky-300 border-sky-500/30 bg-sky-500/10",
  pending: "text-amber-300 border-amber-500/30 bg-amber-500/10",
  failed: "text-rose-300 border-rose-500/30 bg-rose-500/10",
  error: "text-rose-300 border-rose-500/30 bg-rose-500/10",
  default: "text-zinc-300 border-white/10 bg-white/5",
};

/** A status chip; tone derived from common backend status strings. */
export function StatusPill({ status }: { status: string }) {
  const tone = PILL_TONES[status.toLowerCase()] ?? PILL_TONES.default;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[9px] font-mono uppercase tracking-widest",
        tone,
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
      {status}
    </span>
  );
}

export function EmptyState({ message, icon }: { message: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <div className="text-zinc-600">{icon ?? <Inbox className="w-7 h-7" />}</div>
      <p className="text-[12px] text-zinc-500 max-w-sm">{message}</p>
    </div>
  );
}

/**
 * Render-state boundary for a React Query result. Keeps every screen's
 * loading / error / empty handling identical and explicit (coding-style:
 * handle errors at every level; never silently swallow).
 */
export function QueryBoundary<T>({
  isLoading,
  error,
  data,
  isEmpty,
  emptyMessage,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  data: T | undefined;
  isEmpty?: (data: T) => boolean;
  emptyMessage: string;
  children: (data: T) => ReactNode;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-zinc-500 text-[12px]">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-rose-300">
        <AlertTriangle className="w-6 h-6" />
        <p className="text-[12px]">{error instanceof Error ? error.message : "Request failed"}</p>
      </div>
    );
  }
  if (data === undefined) return <EmptyState message={emptyMessage} />;
  if (isEmpty?.(data)) return <EmptyState message={emptyMessage} />;
  return <>{children(data)}</>;
}
