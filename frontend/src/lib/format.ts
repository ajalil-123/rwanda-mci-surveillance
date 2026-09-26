import { format, isValid, parseISO } from "date-fns";

const numberFormatter = new Intl.NumberFormat("en-US");

export function formatNumber(value: number | null | undefined): string {
  return numberFormatter.format(value ?? 0);
}

/** "road_accident" → "road accident"; null → "unknown". */
export function formatIncidentType(type: string | null | undefined): string {
  return type ? type.replace(/_/g, " ") : "unknown";
}

/** ISO date string → "yyyy-MM-dd", or "—" when missing/unparseable. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = parseISO(value);
  return isValid(d) ? format(d, "yyyy-MM-dd") : "—";
}

/** The event date if known, otherwise when the article was detected. */
export function incidentDate(i: { event_date: string | null; detected_at: string }): string {
  return i.event_date || i.detected_at;
}

export function isKnownDistrict(district: string | null | undefined): district is string {
  return Boolean(district) && district !== "Unknown";
}

export const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
