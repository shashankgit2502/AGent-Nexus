"use client";

/**
 * Client-side login gate (Bug 1) — faithful to the reference `App.tsx` `isLoggedIn`
 * flow. There is **no real backend auth** in v1: the landing page shows a LOGIN
 * button; clicking it flips a persisted client flag and reveals the dashboard;
 * logout returns to the landing.
 *
 * The flag is persisted to `sessionStorage` (Requirement 3): a *newly launched*
 * app — a fresh browser session, e.g. a new tab/window — always starts on the
 * landing page, while a refresh within the same session still keeps the user
 * logged in (no flash, no surprise logout mid-task). `localStorage` would have
 * carried logged-in state across launches and dropped users straight onto the
 * dashboard, which is the behaviour we are fixing.
 *
 * This is deliberately not IdP auth (the DB schema supports that later, TECHNICAL
 * §11.1); it replicates the reference UX for the hackathon.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "nexagi_logged_in";

interface AuthState {
  /** Whether the user has "logged in" (client-side flag). */
  isLoggedIn: boolean;
  /** True once the persisted flag has been read on the client (avoids flash). */
  hydrated: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  // Read the persisted flag once on mount (sessionStorage is client-only and
  // scoped to this browser session, so a fresh launch starts logged out).
  useEffect(() => {
    try {
      setIsLoggedIn(window.sessionStorage.getItem(STORAGE_KEY) === "true");
    } catch {
      // Private mode / disabled storage: stay logged out, still hydrate.
    }
    setHydrated(true);
  }, []);

  const login = useCallback(() => {
    setIsLoggedIn(true);
    try {
      window.sessionStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // Non-fatal: in-memory flag still gates the UI for this session.
    }
  }, []);

  const logout = useCallback(() => {
    setIsLoggedIn(false);
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // Non-fatal.
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ isLoggedIn, hydrated, login, logout }),
    [isLoggedIn, hydrated, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
