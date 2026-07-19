"use client";

/**
 * Client providers (React Query).
 *
 * React Query owns REST DTO caching (locked decision: REST → React Query;
 * streaming → Zustand, never mixed). The `QueryClient` is created once per
 * browser session inside state so it survives re-renders but is not shared
 * across requests on the server.
 */
import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/features/auth/use-auth";
import { NotificationsProvider } from "@/features/notifications/use-notifications";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <NotificationsProvider>{children}</NotificationsProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
