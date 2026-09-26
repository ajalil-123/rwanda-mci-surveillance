/** Severity 1–5 as computed by backend/nlp.py. Colours match tailwind `severity.*`. */
export const SEVERITY_LEVELS = {
  1: { label: "Minimal", color: "#484f58", className: "bg-severity-1" },
  2: { label: "Low", color: "#d29922", className: "bg-severity-2" },
  3: { label: "Moderate", color: "#db6d28", className: "bg-severity-3" },
  4: { label: "High", color: "#f85149", className: "bg-severity-4" },
  5: { label: "Critical", color: "#8b0000", className: "bg-severity-5" },
} as const;

export type SeverityLevel = keyof typeof SEVERITY_LEVELS;

export const SEVERITY_ORDER: readonly SeverityLevel[] = [1, 2, 3, 4, 5];

export function clampSeverity(level: number | null | undefined): SeverityLevel {
  const n = Math.round(level ?? 1);
  return (n < 1 ? 1 : n > 5 ? 5 : n) as SeverityLevel;
}
