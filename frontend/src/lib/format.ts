import { format, isValid, parseISO } from "date-fns";

const numberFormatter = new Intl.NumberFormat("en-US");

export function formatNumber(value: number | null | undefined): string {
  return numberFormatter.format(value ?? 0);
}

/** Sentence case: "road accident" → "Road accident". */
export function sentenceCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

/** "road_accident" → "Road accident"; null → "Unknown". */
export function formatIncidentType(type: string | null | undefined): string {
  return type ? sentenceCase(type.replace(/_/g, " ")) : "Unknown";
}

const DOMAIN_RE = /^[\w-]+(\.[\w-]+)+$/i;

/**
 * Strips publisher noise from a scraped headline so only the incident name remains:
 *   "Six killed in Karongi road accident| The New Times - newtimes.co.rw" → "Six killed in Karongi road accident"
 *   "Rwanda: Bukavu - 24 Killed ... - allAfrica.com" → "Bukavu - 24 Killed ..."
 */
export function cleanTitle(title: string, sourceName?: string | null): string {
  const source = sourceName?.trim().toLowerCase() ?? "";
  let t = title.trim();
  for (;;) {
    // Anything after a pipe is a site name
    const pipe = t.lastIndexOf("|");
    if (pipe > 0) {
      t = t.slice(0, pipe).trim();
      continue;
    }
    // Trailing " - Publisher" / " - site.com"
    const dash = t.lastIndexOf(" - ");
    if (dash > 0) {
      const tail = t.slice(dash + 3).trim().toLowerCase();
      if (DOMAIN_RE.test(tail) || (source && (tail === source || source.includes(tail) || tail.includes(source)))) {
        t = t.slice(0, dash).trim();
        continue;
      }
    }
    break;
  }
  // allAfrica-style "Rwanda: " prefix
  t = t.replace(/^rwanda\s*:\s*/i, "");
  return t || title;
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
