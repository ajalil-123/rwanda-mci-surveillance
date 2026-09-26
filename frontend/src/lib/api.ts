/**
 * api.ts — client-side fetchers for the dashboard's SWR hooks.
 *
 * Calls same-origin route handlers (src/app/api/data/[resource]) which query
 * Neon on the server; the NextAuth session cookie authenticates each request.
 */
import { signIn } from "next-auth/react";
import type {
  CfrRow,
  HeatmapCell,
  Hotspot,
  Incident,
  MapIncident,
  MciHotspot,
  MciStats,
  MonthlyPoint,
  PeakMonthsSummary,
  SeasonalPoint,
  TierSummary,
  YoyRow,
} from "./types";

export type * from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(resource: string, params?: Record<string, number>): Promise<T> {
  const query = params ? `?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))}` : "";
  const res = await fetch(`/api/data/${resource}${query}`);
  if (!res.ok) {
    // Session expired mid-visit — back through sign-in, returning to this page
    if (res.status === 401) void signIn();
    throw new ApiError(res.status, `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

/** A user-facing explanation of why a data request failed. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Redirecting to sign in…";
    if (error.status === 404) return "Data service not found. This deployment is out of date. Redeploy the latest version.";
    if (error.status >= 500) return "The database could not be queried. Check the server's DATABASE_URL and try again.";
    return `Could not load data (HTTP ${error.status}).`;
  }
  return "Network error. Check your connection and try again.";
}

export const api = {
  dataAll: () => get<Incident[]>("incidents"),
  incidentsMap: (minDeaths = 0) => get<MapIncident[]>("map", { min_deaths: minDeaths }),
  hotspots: () => get<Hotspot[]>("hotspots"),
  mciHotspots: () => get<MciHotspot[]>("mci-hotspots"),
  mciStats: () => get<MciStats>("mci-stats"),
  monthly: (years = 5) => get<MonthlyPoint[]>("monthly", { years }),
  seasonal: () => get<SeasonalPoint[]>("seasonal"),
  heatmap: () => get<HeatmapCell[]>("heatmap"),
  cfr: () => get<CfrRow[]>("cfr"),
  yoy: () => get<YoyRow[]>("yoy"),
  peakMonths: () => get<PeakMonthsSummary>("peak-months"),
  sourceTiers: () => get<TierSummary[]>("source-tiers"),
};
