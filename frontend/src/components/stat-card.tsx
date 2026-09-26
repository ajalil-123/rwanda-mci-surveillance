import type { ReactNode } from "react";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const ACCENTS = {
  primary: "text-primary",
  destructive: "text-destructive",
  warning: "text-amber-600",
  muted: "text-muted-foreground",
} as const;

export function StatCard({
  label,
  value,
  accent = "primary",
  icon,
  hint,
  loading = false,
}: {
  label: string;
  value: number | string | null | undefined;
  accent?: keyof typeof ACCENTS;
  icon?: ReactNode;
  hint?: string;
  /** Show a pulsing placeholder instead of the value while data loads. */
  loading?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      {loading ? (
        <div role="status" aria-label={`Loading ${label.toLowerCase()}`} className="mt-2 space-y-2">
          <div className="h-8 w-20 animate-pulse rounded-md bg-muted" />
          {hint !== undefined ? <div className="h-3 w-28 animate-pulse rounded bg-muted" /> : null}
        </div>
      ) : (
        <>
          <div className={cn("mt-2 font-mono text-2xl font-semibold tabular-nums", ACCENTS[accent])}>
            {typeof value === "string" ? value : value == null ? "—" : formatNumber(value)}
          </div>
          {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
        </>
      )}
    </div>
  );
}
