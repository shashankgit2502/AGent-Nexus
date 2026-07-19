"use client";

/**
 * Global header nav — ported from the reference App.tsx visual language
 * (obsidian bar, emerald accent, mono uppercase labels), but driven by real
 * Next App Router routes instead of the reference's `useState` page switch.
 *
 * Primary routes live in a glassmorphic pill with a springy shared
 * `layoutId="activeNavIndicator"` underline. The auxiliary routes are collapsed
 * into a centralized **"Aux Engines"** dropdown (icons + bold labels + inline
 * metadata) to keep the bar uncluttered. The dropdown closes on outside click,
 * Escape, or navigation. The glowing notification bell (bounce + slide-down pane)
 * is the existing `NotificationBell`.
 *
 * The reference's fake login, simulated agent toasts, and notification matrix
 * are intentionally NOT ported — they were demo scaffolding. The live nav
 * highlights the active route via `usePathname`.
 */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Cpu,
  Layers,
  Users,
  Bot,
  Database,
  HardDrive,
  Sliders,
  Settings,
  ChevronDown,
  History,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/features/auth/use-auth";
import { NotificationBell } from "@/components/notifications/notification-bell";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Cpu;
}

interface AuxNavItem extends NavItem {
  /** Short descriptive metadata rendered under the label in the dropdown. */
  desc: string;
}

const PRIMARY: NavItem[] = [
  { href: "/", label: "Dashboard", icon: Layers },
  { href: "/workspace", label: "Session Workspace", icon: Cpu },
  { href: "/teams", label: "Teams Builder", icon: Users },
  { href: "/chat", label: "Chat", icon: Bot },
];

const AUX: AuxNavItem[] = [
  { href: "/knowledge", label: "Knowledge Base", desc: "Central vector indices", icon: Database },
  { href: "/memory", label: "Memory Explorer", desc: "LTM cognitive dumps", icon: HardDrive },
  { href: "/settings/ai", label: "Inference Tuning", desc: "Model configs & parameters", icon: Sliders },
  { href: "/history", label: "Saved Sessions", desc: "Historic runs archiver", icon: History },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "relative px-3.5 py-2 text-[10.5px] font-bold tracking-widest uppercase transition-all rounded-xl flex items-center gap-1.5 select-none",
        active
          ? "text-white bg-white/5 border border-white/10 shadow-[0_0_12px_rgba(255,255,255,0.03)]"
          : "text-zinc-400 hover:text-white hover:bg-white/5 border border-transparent",
      )}
    >
      <Icon className={cn("w-3.5 h-3.5", active ? "text-[#10b981]" : "text-zinc-500")} />
      <span>{item.label}</span>
      {active && (
        <motion.div
          layoutId="activeNavIndicator"
          className="absolute bottom-[-1px] left-3.5 right-3.5 h-[2px] bg-[#10b981] rounded-full"
          transition={{ type: "spring", stiffness: 350, damping: 30 }}
        />
      )}
    </Link>
  );
}

/**
 * "Aux Engines" — a centralized dropdown that collapses the auxiliary routes.
 * Self-contained open state with outside-click / Escape / route-change closing.
 */
function AuxEnginesMenu({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const anyActive = AUX.some((item) => isActive(pathname, item.href));

  // Close on outside click or Escape while open.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Close whenever the active route changes (e.g. after selecting an item).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cn(
          "relative px-3.5 py-2 text-[10.5px] font-bold tracking-widest uppercase transition-all rounded-xl flex items-center gap-1.5 select-none cursor-pointer",
          anyActive || open
            ? "text-white bg-white/5 border border-white/10"
            : "text-zinc-400 hover:text-white hover:bg-white/5 border border-transparent",
        )}
      >
        <Settings className={cn("w-3.5 h-3.5", anyActive ? "text-[#10b981]" : "text-zinc-500")} />
        <span>Aux Engines</span>
        <ChevronDown
          className={cn("w-3 h-3 text-zinc-500 transition-transform duration-200", open && "rotate-180")}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full mt-2 w-64 bg-[#0a0f0c] border border-white/10 rounded-xl p-2 shadow-[0_12px_40px_rgba(0,0,0,0.85)] z-[60]"
          >
            <div className="px-3 py-1.5 mb-1.5 border-b border-white/5">
              <p className="text-[8.5px] font-mono text-zinc-500 tracking-widest uppercase">
                Platform Auxiliary Systems
              </p>
            </div>
            <div className="space-y-1">
              {AUX.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    role="menuitem"
                    onClick={() => setOpen(false)}
                    className={cn(
                      "w-full text-left px-3 py-2 rounded-lg transition-all flex items-start gap-2.5",
                      active
                        ? "bg-[#10b981]/15 text-white border-l-2 border-[#10b981]"
                        : "text-zinc-400 hover:bg-white/5 hover:text-white",
                    )}
                  >
                    <Icon
                      className={cn("w-4 h-4 mt-0.5 shrink-0", active ? "text-[#10b981]" : "text-zinc-500")}
                    />
                    <div className="min-w-0">
                      <p className="text-[10px] uppercase font-bold tracking-wider">{item.label}</p>
                      <p className="text-[8.5px] text-zinc-500 truncate mt-0.5">{item.desc}</p>
                    </div>
                  </Link>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const { isLoggedIn, hydrated, login, logout } = useAuth();

  return (
    <header className="sticky top-0 z-50 h-20 bg-[#050506]/75 backdrop-blur-2xl border-b border-white/10">
      <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto h-full flex items-center justify-between px-6 md:px-12">
        {/* Logo — when logged out it is a non-navigating brand (the gate hides routes) */}
        <Link href="/" className="flex items-center gap-3 group shrink-0">
          <div className="w-8 h-8 rounded bg-white flex items-center justify-center text-black font-mono font-black text-xs shadow-[0_0_20px_rgba(255,255,255,0.2)] group-hover:scale-105 transition-all">
            Nx
          </div>
          <span className="text-[12px] font-extrabold tracking-[0.25em] text-white uppercase">
            NEX AGI
          </span>
          {isLoggedIn && (
            <span className="px-2 py-0.5 bg-[#10b981]/15 border border-[#10b981]/25 text-[#10b981] text-[8px] font-mono rounded font-bold uppercase tracking-wider hidden md:inline select-none">
              v1.4
            </span>
          )}
        </Link>

        {/* Nav is only shown to authenticated users (reference parity). */}
        {hydrated && isLoggedIn ? (
          <>
            <nav className="hidden lg:flex items-center gap-1.5 px-4 py-1.5 bg-[#080d0a]/60 border border-white/5 rounded-2xl">
              {PRIMARY.map((item) => (
                <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
              ))}
              <div className="w-[1px] h-4 bg-white/10 mx-2" />
              <AuxEnginesMenu pathname={pathname} />
            </nav>

            {/* Compact nav (smaller screens): primary only */}
            <nav className="flex lg:hidden items-center gap-1 overflow-x-auto">
              {PRIMARY.map((item) => (
                <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
              ))}
            </nav>

            <div className="flex items-center gap-3 shrink-0">
              <NotificationBell />
              <button
                type="button"
                onClick={logout}
                className="flex items-center gap-2 px-3.5 py-2 bg-neutral-900 border border-white/10 text-stone-300 text-[10.5px] tracking-wider uppercase rounded-xl hover:text-white hover:border-white/20 transition-all cursor-pointer"
                title="Log out"
              >
                <LogOut className="w-3.5 h-3.5 text-zinc-500" />
                <span className="hidden md:inline">Exit Portal</span>
              </button>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-3">
            <span className="hidden md:inline text-[10px] uppercase font-mono tracking-widest text-[#10b981]/80 bg-[#10b981]/10 px-3 py-1.5 rounded-lg border border-emerald-500/10">
              Secured Agentic Convergence
            </span>
            <button
              type="button"
              onClick={login}
              className="px-5 py-2.5 bg-white hover:bg-zinc-200 text-black font-black text-[10.5px] tracking-widest uppercase rounded-lg shadow-[0_4px_24px_rgba(255,255,255,0.15)] transition-all cursor-pointer hover:scale-[1.01] active:scale-95"
            >
              Login
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
