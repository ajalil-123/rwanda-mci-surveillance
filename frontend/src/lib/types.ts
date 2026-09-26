/**
 * Response shapes shared by the server queries (src/server/queries.ts)
 * and the client fetchers (src/lib/api.ts).
 */

export type SourceTier = 1 | 2 | 3;

export interface Incident {
  id: number;
  title: string;
  event_date: string | null;
  detected_at: string;
  incident_type: string | null;
  district: string | null;
  province: string | null;
  latitude: number | null;
  longitude: number | null;
  deaths: number;
  injured: number;
  missing: number;
  severity: number;
  source_name: string | null;
  source_url: string | null;
  source_tier: SourceTier;
  ai_summary: string | null;
  status: string | null;
}

export type MapIncident = Pick<
  Incident,
  | "id"
  | "title"
  | "district"
  | "province"
  | "severity"
  | "deaths"
  | "injured"
  | "incident_type"
  | "event_date"
  | "detected_at"
  | "source_name"
  | "source_tier"
  | "ai_summary"
> & { latitude: number; longitude: number };

export interface Hotspot {
  district: string;
  province: string | null;
  incident_count: number;
  total_deaths: number;
  total_injured: number;
  types: string | null;
  risk_score: number;
}

export interface MciHotspot {
  district: string;
  province: string | null;
  incident_count: number;
  total_deaths: number;
  total_injured: number;
  max_deaths: number;
  types: string | null;
}

export interface MonthlyPoint {
  month: string;
  incidents: number;
  deaths: number;
  injured: number;
  deaths_3m_avg: number;
}

export interface SeasonalPoint {
  month_num: number;
  month_name: string;
  avg_incidents: number;
  avg_deaths: number;
}

export interface HeatmapCell {
  year: string;
  month: number;
  incidents: number;
  deaths: number;
}

export interface CfrRow {
  incident_type: string | null;
  incidents: number;
  case_fatality_rate: number;
}

export interface YoyRow {
  year: string;
  incidents: number;
  deaths: number;
  inc_pct_change: number | null;
  dth_pct_change: number | null;
}

export interface PeakMonthsSummary {
  peak_month: string | null;
  peak_month_avg_inc: number | null;
  low_month: string | null;
  rainy_vs_dry_ratio: number | null;
  worst_year: string | null;
  worst_year_deaths: number | null;
}

export interface TierSummary {
  tier: SourceTier;
  label: string;
  credibility: string;
  incidents: number;
  deaths: number;
  unique_sources: number;
}

export interface MciBucket {
  count: number;
  pct: number;
  deaths: number;
  injured: number;
}

export interface MciStats {
  threshold: number;
  mci: MciBucket;
  non_mci: MciBucket;
  worst_mci: {
    title: string;
    event_date: string | null;
    district: string | null;
    deaths: number;
    incident_type: string | null;
  } | null;
}
