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
}: {
  label: string;
  value: number | string | null | undefined;
  accent?: keyof typeof ACCENTS;
  icon?: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <div className={cn("mt-2 font-mono text-2xl font-semibold tabular-nums", ACCENTS[accent])}>
        {typeof value === "string" ? value : value == null ? "—" : formatNumber(value)}
      </div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}
