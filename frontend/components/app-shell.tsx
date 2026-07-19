"use client";

/**
 * Client shell (Bug 1) — decides between the public landing page and the
 * authenticated app, replicating the reference `App.tsx` split:
 *   - logged out → `LandingView` (route content is hidden behind the gate)
 *   - logged in  → the real app (`SiteHeader` nav + the routed page)
 *
 * Rendering waits for `hydrated` so a logged-in user never flashes the landing
 * page on refresh. The header + footer chrome is shared across both states; the
 * header itself switches its contents based on auth (see SiteHeader).
 */
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/site-header";
import { LandingView } from "@/components/landing-view";
import { NotificationOverlay } from "@/components/notifications/notification-overlay";
import { useAuth } from "@/features/auth/use-auth";

export function AppShell({ children }: { children: ReactNode }) {
  const { isLoggedIn, hydrated } = useAuth();

  return (
    <>
      <SiteHeader />
      <main className="flex-1 flex flex-col items-center relative z-10 w-full">
        {!hydrated ? null : isLoggedIn ? children : <LandingView />}
      </main>
      <footer className="artistic-pane !border-x-0 !border-b-0 py-6 text-center text-[10.5px] text-zinc-500 font-mono relative z-10 bg-black/40 backdrop-blur-md">
        <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4 px-6 md:px-12">
          <p>© 2026 NEX AGI. Human engineered, agentic state-machine orchestrated.</p>
          <div className="flex justify-center gap-4 text-zinc-600">
            <span>Status: Continuous Convergence</span>
            <span>•</span>
            <span>Region: Node-Bus</span>
          </div>
        </div>
      </footer>

      {/* Global floating toast overlay (renders only when enabled in the bell pane). */}
      <NotificationOverlay />
    </>
  );
}
