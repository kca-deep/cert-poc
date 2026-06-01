"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

/**
 * App-wide client providers.
 * - React Query holds server state (mock now, FastAPI later via lib/api.ts).
 * - The app is dark-only via <html class="dark"> (single source of truth).
 *   We intentionally drop next-themes' ThemeProvider so nothing mutates the
 *   <html> class/color-scheme on the client → no hydration mismatch. The
 *   Toaster is pinned to the dark theme directly.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        {children}
        <Toaster theme="dark" position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
