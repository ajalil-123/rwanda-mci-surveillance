import { SEVERITY_LEVELS, clampSeverity } from "@/lib/severity";
import { cn } from "@/lib/utils";

export function SeverityDot({
  level,
  showLabel = false,
  className,
}: {
  level: number | null | undefined;
  showLabel?: boolean;
  className?: string;
}) {
  const s = clampSeverity(level);
  const { label, className: color } = SEVERITY_LEVELS[s];
  const text = `Severity ${s}: ${label}`;

  return (
    <span className={cn("inline-flex items-center gap-1.5", className)} title={text}>
      <span aria-hidden className={cn("inline-block h-2.5 w-2.5 rounded-full", color)} />
      {showLabel ? (
        <span className="text-xs text-muted-foreground">{label}</span>
      ) : (
        <span className="sr-only">{text}</span>
      )}
    </span>
  );
}
