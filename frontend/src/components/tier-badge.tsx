import type { SourceTier } from "@/lib/api";
import { cn } from "@/lib/utils";

const TIER_STYLES = {
  1: {
    className: "bg-green-500/15 border-green-500/30 text-green-700 dark:text-green-400",
    label: "T1",
    tip: "Official Communication",
  },
  2: {
    className: "bg-blue-500/15 border-blue-500/30 text-blue-700 dark:text-blue-400",
    label: "T2",
    tip: "Official Journalism",
  },
  3: {
    className: "bg-amber-500/15 border-amber-500/30 text-amber-700 dark:text-amber-500",
    label: "T3",
    tip: "Other Source",
  },
} as const;

export function TierBadge({ tier, size = "sm" }: { tier: SourceTier | null; size?: "sm" | "md" }) {
  // Backend defaults unknown sources to tier 3
  const s = TIER_STYLES[tier ?? 3];
  return (
    <span
      title={s.tip}
      className={cn(
        "inline-flex items-center rounded border font-mono font-bold tracking-wide",
        s.className,
        size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
      )}
    >
      {s.label}
    </span>
  );
}
