"use client";

import type { ReactNode } from "react";
import { SessionProvider } from "next-auth/react";
import { SWRConfig } from "swr";

const SWR_OPTIONS = {
  refreshInterval: 60_000, // backend scrapes every 30 min; 1 min keeps views fresh cheaply
  revalidateOnFocus: false,
  dedupingInterval: 10_000,
} as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <SWRConfig value={SWR_OPTIONS}>{children}</SWRConfig>
    </SessionProvider>
  );
}
