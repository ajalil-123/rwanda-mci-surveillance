import "server-only";
import { db } from "./db";
import { MONTH_NAMES } from "@/lib/format";
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
  SourceTier,
  TierSummary,
  YoyRow,
} from "@/lib/types";

/*
 * All analytics read the `verified_incidents` view (scraper/schema.sql), which
 * hides rows Claude rejected and exposes `occurred_at` = event date, falling
 * back to detection date.
 *
 * Postgres COUNT/SUM return bigint/numeric, which the driver hands back as
 * strings — every aggregate is cast to ::int or ::float8 so JSON gets numbers.
 */

/** Must match MCI_THRESHOLD in scraper/jobs.py. */
export const MCI_THRESHOLD = 3;

/** Rwanda's rainy seasons: March–May and October–November. */
const RAINY_MONTHS = new Set([3, 4, 5, 10, 11]);

const TIER_INFO: Record<SourceTier, { label: string; credibility: string }> = {
  1: { label: "Official Communication", credibility: "Highest" },
  2: { label: "Official Journalism / Social Media", credibility: "High" },
  3: { label: "Other Sources", credibility: "Moderate — verify before action" },
};

function pct(part: number, total: number): number {
  return Math.round((1000 * part) / Math.max(total, 1)) / 10;
}

export async function allIncidents(): Promise<Incident[]> {
  return (await db()`
    SELECT id, title, event_date, detected_at, incident_type, district, province,
           latitude, longitude, deaths, injured, missing, severity,
           source_name, source_url, source_tier, ai_summary, status
    FROM verified_incidents
    ORDER BY occurred_at DESC
  `) as Incident[];
}

export async function mapIncidents(minDeaths: number): Promise<MapIncident[]> {
  return (await db()`
    SELECT id, title, district, province, latitude, longitude, severity, deaths, injured,
           incident_type, event_date, detected_at, source_name, source_tier, ai_summary
    FROM verified_incidents
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND deaths >= ${minDeaths}
    ORDER BY deaths DESC, detected_at DESC
  `) as MapIncident[];
}

export async function hotspots(): Promise<Hotspot[]> {
  // risk score = incidents + 2 × deaths + 1.5 × average severity
  return (await db()`
    SELECT district,
           MAX(province)                              AS province,
           COUNT(*)::int                              AS incident_count,
           SUM(deaths)::int                           AS total_deaths,
           SUM(injured)::int                          AS total_injured,
           string_agg(DISTINCT incident_type, ',')    AS types,
           ROUND((COUNT(*) + 2 * SUM(deaths) + 1.5 * AVG(severity))::numeric, 1)::float8 AS risk_score
    FROM verified_incidents
    WHERE district <> '' AND district <> 'Unknown'
    GROUP BY district
    ORDER BY risk_score DESC
  `) as Hotspot[];
}

export async function mciHotspots(): Promise<MciHotspot[]> {
  return (await db()`
    SELECT district,
           MAX(province)                           AS province,
           COUNT(*)::int                           AS incident_count,
           SUM(deaths)::int                        AS total_deaths,
           SUM(injured)::int                       AS total_injured,
           MAX(deaths)::int                        AS max_deaths,
           string_agg(DISTINCT incident_type, ',') AS types
    FROM verified_incidents
    WHERE deaths >= ${MCI_THRESHOLD} AND district <> '' AND district <> 'Unknown'
    GROUP BY district
    ORDER BY total_deaths DESC
    LIMIT 20
  `) as MciHotspot[];
}

export async function monthlyTrend(years: number): Promise<MonthlyPoint[]> {
  const since = new Date(Date.now() - years * 365 * 86_400_000).toISOString().slice(0, 10);
  return (await db()`
    SELECT month, incidents, deaths,
           ROUND(AVG(deaths) OVER (ORDER BY month ROWS 2 PRECEDING), 1)::float8 AS deaths_3m_avg
    FROM (
      SELECT substr(occurred_at, 1, 7) AS month,
             COUNT(*)::int             AS incidents,
             SUM(deaths)::int          AS deaths
      FROM verified_incidents
      WHERE occurred_at >= ${since} AND occurred_at ~ '^[0-9]{4}-(0[1-9]|1[0-2])'
      GROUP BY 1
    ) m
    ORDER BY month
  `) as MonthlyPoint[];
}

export async function seasonalPattern(): Promise<SeasonalPoint[]> {
  const rows = (await db()`
    SELECT substr(occurred_at, 6, 2)::int AS month_num,
           ROUND(COUNT(*)::numeric / GREATEST(COUNT(DISTINCT substr(occurred_at, 1, 4)), 1), 1)::float8     AS avg_incidents,
           ROUND(SUM(deaths)::numeric / GREATEST(COUNT(DISTINCT substr(occurred_at, 1, 4)), 1), 1)::float8  AS avg_deaths
    FROM verified_incidents
    WHERE occurred_at ~ '^[0-9]{4}-(0[1-9]|1[0-2])'
    GROUP BY 1
    ORDER BY 1
  `) as Omit<SeasonalPoint, "month_name">[];
  return rows.map((r) => ({ ...r, month_name: MONTH_NAMES[r.month_num - 1] }));
}

export async function monthlyHeatmap(): Promise<HeatmapCell[]> {
  return (await db()`
    SELECT substr(occurred_at, 1, 4)       AS year,
           substr(occurred_at, 6, 2)::int  AS month,
           COUNT(*)::int                   AS incidents,
           SUM(deaths)::int                AS deaths
    FROM verified_incidents
    WHERE occurred_at >= '2015' AND occurred_at ~ '^[0-9]{4}-(0[1-9]|1[0-2])'
    GROUP BY 1, 2
    ORDER BY 1, 2
  `) as HeatmapCell[];
}

export async function caseFatalityRate(): Promise<CfrRow[]> {
  return (await db()`
    SELECT incident_type,
           COUNT(*)::int AS incidents,
           ROUND(SUM(deaths) * 100.0 / NULLIF(SUM(deaths + injured), 0), 1)::float8 AS case_fatality_rate
    FROM verified_incidents
    WHERE deaths > 0 OR injured > 0
    GROUP BY incident_type
    ORDER BY case_fatality_rate DESC NULLS LAST
  `) as CfrRow[];
}

export async function yearOverYear(): Promise<YoyRow[]> {
  return (await db()`
    SELECT year, incidents, deaths,
           ROUND((incidents - LAG(incidents) OVER w) * 100.0 / NULLIF(LAG(incidents) OVER w, 0), 1)::float8 AS inc_pct_change,
           ROUND((deaths - LAG(deaths) OVER w) * 100.0 / NULLIF(LAG(deaths) OVER w, 0), 1)::float8           AS dth_pct_change
    FROM (
      SELECT substr(occurred_at, 1, 4) AS year, COUNT(*)::int AS incidents, SUM(deaths)::int AS deaths
      FROM verified_incidents
      WHERE occurred_at ~ '^[0-9]{4}'
      GROUP BY 1
    ) y
    WINDOW w AS (ORDER BY year)
    ORDER BY year
  `) as YoyRow[];
}

export async function peakMonths(): Promise<PeakMonthsSummary> {
  const [seasonal, yearly] = await Promise.all([seasonalPattern(), yearOverYear()]);

  const byIncidents = [...seasonal].sort((a, b) => b.avg_incidents - a.avg_incidents);
  const rainy = seasonal.filter((s) => RAINY_MONTHS.has(s.month_num));
  const dry = seasonal.filter((s) => !RAINY_MONTHS.has(s.month_num));
  const avg = (xs: SeasonalPoint[]) => xs.reduce((sum, s) => sum + s.avg_incidents, 0) / xs.length;
  const worst = yearly.reduce<YoyRow | null>((w, y) => (!w || y.deaths > w.deaths ? y : w), null);

  return {
    peak_month: byIncidents[0]?.month_name ?? null,
    peak_month_avg_inc: byIncidents[0]?.avg_incidents ?? null,
    low_month: byIncidents.at(-1)?.month_name ?? null,
    rainy_vs_dry_ratio:
      rainy.length && dry.length && avg(dry) > 0 ? Math.round((avg(rainy) / avg(dry)) * 100) / 100 : null,
    worst_year: worst?.year ?? null,
    worst_year_deaths: worst?.deaths ?? null,
  };
}

export async function sourceTiers(): Promise<TierSummary[]> {
  const rows = (await db()`
    SELECT source_tier                  AS tier,
           COUNT(*)::int                AS incidents,
           SUM(deaths)::int             AS deaths,
           COUNT(DISTINCT source_name)::int AS unique_sources
    FROM verified_incidents
    GROUP BY source_tier
  `) as Pick<TierSummary, "tier" | "incidents" | "deaths" | "unique_sources">[];

  return ([1, 2, 3] as const).map((tier) => {
    const row = rows.find((r) => r.tier === tier);
    return {
      tier,
      ...TIER_INFO[tier],
      incidents: row?.incidents ?? 0,
      deaths: row?.deaths ?? 0,
      unique_sources: row?.unique_sources ?? 0,
    };
  });
}

export async function mciStats(): Promise<MciStats> {
  const sql = db();
  const [[totals], [worst]] = await Promise.all([
    sql`
      SELECT COUNT(*)::int                                                      AS total,
             COUNT(*) FILTER (WHERE deaths >= ${MCI_THRESHOLD})::int            AS mci_count,
             COALESCE(SUM(deaths)  FILTER (WHERE deaths >= ${MCI_THRESHOLD}), 0)::int AS mci_deaths,
             COALESCE(SUM(injured) FILTER (WHERE deaths >= ${MCI_THRESHOLD}), 0)::int AS mci_injured,
             COALESCE(SUM(deaths)  FILTER (WHERE deaths <  ${MCI_THRESHOLD}), 0)::int AS non_deaths,
             COALESCE(SUM(injured) FILTER (WHERE deaths <  ${MCI_THRESHOLD}), 0)::int AS non_injured
      FROM verified_incidents
    `,
    sql`
      SELECT title, event_date, district, deaths, incident_type
      FROM verified_incidents
      WHERE deaths >= ${MCI_THRESHOLD}
      ORDER BY deaths DESC
      LIMIT 1
    `,
  ]);

  const t = totals as Record<string, number>;
  const nonCount = t.total - t.mci_count;
  return {
    threshold: MCI_THRESHOLD,
    mci: { count: t.mci_count, pct: pct(t.mci_count, t.total), deaths: t.mci_deaths, injured: t.mci_injured },
    non_mci: { count: nonCount, pct: pct(nonCount, t.total), deaths: t.non_deaths, injured: t.non_injured },
    worst_mci: (worst as MciStats["worst_mci"]) ?? null,
  };
}
