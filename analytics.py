"""
analytics.py — Trend analysis, hotspot detection, and predictive insights.
Pure Python + SQLite, no ML libraries required.
Uses moving averages, seasonal decomposition, and district risk scoring.
"""
import math
from datetime import datetime, timedelta
from collections import defaultdict
from database import get_db

# ── Helper ────────────────────────────────────────────────────────────────────
def rows_to_list(rows):
    return [dict(r) for r in rows]

# ── 1. SUMMARY STATS ─────────────────────────────────────────────────────────
def get_summary_stats() -> dict:
    conn = get_db()
    total     = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    confirmed = conn.execute("SELECT COUNT(*) FROM incidents WHERE deaths > 0").fetchone()[0]
    deaths    = conn.execute("SELECT SUM(deaths) FROM incidents").fetchone()[0] or 0
    injured   = conn.execute("SELECT SUM(injured) FROM incidents").fetchone()[0] or 0
    missing   = conn.execute("SELECT SUM(missing) FROM incidents").fetchone()[0] or 0
    critical  = conn.execute("SELECT COUNT(*) FROM incidents WHERE severity >= 4").fetchone()[0]
    last_24h  = conn.execute(
        "SELECT COUNT(*) FROM incidents WHERE detected_at >= ?",
        ((datetime.utcnow()-timedelta(hours=24)).isoformat(),)
    ).fetchone()[0]
    last_7d   = conn.execute(
        "SELECT COUNT(*) FROM incidents WHERE detected_at >= ?",
        ((datetime.utcnow()-timedelta(days=7)).isoformat(),)
    ).fetchone()[0]
    last_30d  = conn.execute(
        "SELECT COUNT(*) FROM incidents WHERE detected_at >= ?",
        ((datetime.utcnow()-timedelta(days=30)).isoformat(),)
    ).fetchone()[0]
    sources   = rows_to_list(conn.execute(
        "SELECT media_type, COUNT(*) as cnt FROM incidents GROUP BY media_type"
    ).fetchall())
    conn.close()
    return {
        "total_incidents":    total,
        "with_deaths":        confirmed,
        "total_deaths":       deaths,
        "total_injured":      injured,
        "total_missing":      missing,
        "critical_incidents": critical,
        "last_24h":           last_24h,
        "last_7d":            last_7d,
        "last_30d":           last_30d,
        "by_source":          sources,
    }

# ── 2. INCIDENTS BY TYPE ──────────────────────────────────────────────────────
def by_incident_type() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT incident_type,
               COUNT(*) as count,
               SUM(deaths) as total_deaths,
               SUM(injured) as total_injured,
               AVG(severity) as avg_severity
        FROM incidents
        GROUP BY incident_type
        ORDER BY total_deaths DESC
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 3. DISTRICT HOTSPOTS ──────────────────────────────────────────────────────
def district_hotspots() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT district, province,
               AVG(latitude) as lat, AVG(longitude) as lng,
               COUNT(*) as incident_count,
               SUM(deaths) as total_deaths,
               SUM(injured) as total_injured,
               MAX(severity) as max_severity,
               AVG(severity) as avg_severity,
               GROUP_CONCAT(DISTINCT incident_type) as types
        FROM incidents
        WHERE district != '' AND district != 'Unknown'
        GROUP BY district
        ORDER BY total_deaths DESC
    """).fetchall()
    conn.close()
    result = rows_to_list(rows)
    # compute risk score: weighted combo of count, deaths, severity
    for r in result:
        r["risk_score"] = round(
            (r["incident_count"] * 1.0) +
            (r["total_deaths"] * 2.0) +
            (r["avg_severity"] * 1.5), 1
        )
    result.sort(key=lambda x: x["risk_score"], reverse=True)
    return result

# ── 4. TIME-SERIES TRENDS ─────────────────────────────────────────────────────
def monthly_trend(years_back=5) -> list:
    since = (datetime.utcnow() - timedelta(days=years_back*365)).isoformat()
    conn  = get_db()
    rows  = conn.execute("""
        SELECT substr(COALESCE(event_date, detected_at), 1, 7) as month,
               COUNT(*) as incidents,
               SUM(deaths) as deaths,
               SUM(injured) as injured,
               AVG(severity) as avg_severity
        FROM incidents
        WHERE detected_at >= ?
          AND substr(COALESCE(event_date, detected_at), 1, 7) != ''
        GROUP BY month
        ORDER BY month
    """, (since,)).fetchall()
    conn.close()
    data = rows_to_list(rows)
    # add 3-month rolling average of deaths
    for i, row in enumerate(data):
        window = data[max(0, i-2):i+1]
        row["deaths_3m_avg"] = round(
            sum(w["deaths"] or 0 for w in window) / len(window), 1
        )
    return data

def yearly_trend() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT substr(COALESCE(event_date, detected_at), 1, 4) as year,
               COUNT(*) as incidents,
               SUM(deaths) as deaths,
               SUM(injured) as injured,
               AVG(severity) as avg_severity
        FROM incidents
        WHERE year != '' AND year >= '2015'
        GROUP BY year
        ORDER BY year
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 5. SEASONAL PATTERNS ──────────────────────────────────────────────────────
def seasonal_pattern() -> list:
    """Average incidents per month-of-year to detect seasonal peaks."""
    conn = get_db()
    rows = conn.execute("""
        SELECT substr(COALESCE(event_date, detected_at), 6, 2) as month_num,
               COUNT(*) as total_incidents,
               SUM(deaths) as total_deaths,
               COUNT(DISTINCT substr(COALESCE(event_date, detected_at), 1, 4)) as years_seen
        FROM incidents
        WHERE month_num != '' AND month_num != '00'
        GROUP BY month_num
        ORDER BY month_num
    """).fetchall()
    conn.close()
    month_names = ["","Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    result = []
    for r in rows_to_list(rows):
        m = int(r["month_num"]) if r["month_num"].isdigit() else 0
        if 1 <= m <= 12:
            years = max(r["years_seen"], 1)
            result.append({
                "month_num":  m,
                "month_name": month_names[m],
                "avg_incidents": round(r["total_incidents"] / years, 1),
                "avg_deaths":    round((r["total_deaths"] or 0) / years, 1),
                "total_incidents": r["total_incidents"],
            })
    return result

# ── 6. INCIDENT TYPE TRENDS OVER TIME ────────────────────────────────────────
def type_trend_by_year() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT substr(COALESCE(event_date, detected_at), 1, 4) as year,
               incident_type,
               COUNT(*) as count,
               SUM(deaths) as deaths
        FROM incidents
        WHERE year >= '2015' AND year != ''
        GROUP BY year, incident_type
        ORDER BY year, deaths DESC
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 7. PREDICTION ENGINE ──────────────────────────────────────────────────────
def predict_next_month() -> dict:
    """
    Simple forecasting using weighted moving average of monthly data.
    Returns predicted incident count and deaths for the upcoming month.
    """
    monthly = monthly_trend(years_back=5)
    if len(monthly) < 3:
        return {"predicted_incidents": 0, "predicted_deaths": 0, "confidence": "low"}

    # weighted moving average (more recent = higher weight)
    n = min(6, len(monthly))
    recent = monthly[-n:]
    weights = list(range(1, n+1))
    total_w = sum(weights)

    pred_inc = sum(r["incidents"] * w for r, w in zip(recent, weights)) / total_w
    pred_dth = sum((r["deaths"] or 0) * w for r, w in zip(recent, weights)) / total_w

    # seasonal adjustment
    next_month = (datetime.utcnow().month % 12) + 1
    seasonal   = seasonal_pattern()
    season_map = {s["month_num"]: s["avg_incidents"] for s in seasonal}
    overall_avg = sum(s["avg_incidents"] for s in seasonal) / max(len(seasonal), 1)
    if overall_avg > 0 and next_month in season_map:
        seasonal_factor = season_map[next_month] / overall_avg
        pred_inc *= seasonal_factor
        pred_dth *= seasonal_factor

    confidence = "high" if len(monthly) >= 24 else "medium" if len(monthly) >= 12 else "low"

    return {
        "predicted_incidents": round(pred_inc, 1),
        "predicted_deaths":    round(pred_dth, 1),
        "next_month":          (datetime.utcnow().replace(day=1) + timedelta(days=32)).strftime("%B %Y"),
        "confidence":          confidence,
        "based_on_months":     len(monthly),
    }

def high_risk_districts() -> list:
    """Predict top 5 highest-risk districts for next 30 days."""
    hotspots = district_hotspots()
    seasonal = seasonal_pattern()
    next_month = (datetime.utcnow().month % 12) + 1
    season_map = {s["month_num"]: s["avg_incidents"] for s in seasonal}
    overall_avg = sum(s["avg_incidents"] for s in seasonal) / max(len(seasonal), 1)
    factor = 1.0
    if overall_avg > 0 and next_month in season_map:
        factor = season_map[next_month] / overall_avg

    result = []
    for h in hotspots[:10]:
        # recent trend (last 90 days)
        conn = get_db()
        recent = conn.execute("""
            SELECT COUNT(*) FROM incidents
            WHERE district=? AND detected_at >= ?
        """, (h["district"], (datetime.utcnow()-timedelta(days=90)).isoformat())).fetchone()[0]
        conn.close()

        projected = round((h["incident_count"] / max(1, 12)) * factor, 1)
        result.append({
            "district":           h["district"],
            "province":           h["province"],
            "lat":                h["lat"],
            "lng":                h["lng"],
            "historical_count":   h["incident_count"],
            "historical_deaths":  h["total_deaths"],
            "risk_score":         h["risk_score"],
            "recent_90d":         recent,
            "projected_next_month": projected,
            "dominant_types":     h.get("types","").split(",")[:3],
        })
    return result[:5]

# ── 8. RECENT INCIDENTS LIST ──────────────────────────────────────────────────
def recent_incidents(hours=72, min_severity=1, limit=200) -> list:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conn  = get_db()
    rows  = conn.execute("""
        SELECT * FROM incidents
        WHERE detected_at >= ? AND severity >= ?
        ORDER BY detected_at DESC
        LIMIT ?
    """, (since, min_severity, limit)).fetchall()
    conn.close()
    return rows_to_list(rows)

def all_mapped_incidents(min_deaths=0) -> list:
    """All incidents with coordinates for full map view."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, title, district, province, latitude, longitude,
               severity, deaths, injured, incident_type, event_date,
               detected_at, source_name, source_tier, ai_summary, status
        FROM incidents
        WHERE latitude IS NOT NULL AND deaths >= ?
        ORDER BY deaths DESC, detected_at DESC
    """, (min_deaths,)).fetchall()
    conn.close()
    return rows_to_list(rows)

def scrape_status() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT source, scrape_type,
               MAX(finished_at) as last_run,
               SUM(articles_seen) as total_seen,
               SUM(incidents_added) as total_added
        FROM scrape_log
        GROUP BY source, scrape_type
        ORDER BY last_run DESC
        LIMIT 30
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 9. MONTHLY HEATMAP ───────────────────────────────────────────────────────
def monthly_heatmap() -> list:
    """
    Returns incidents and deaths for every (year, month) combination.
    Used to build a calendar heatmap showing peak months across years.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT
            substr(COALESCE(event_date, detected_at), 1, 4) as year,
            CAST(substr(COALESCE(event_date, detected_at), 6, 2) AS INTEGER) as month,
            COUNT(*) as incidents,
            SUM(deaths) as deaths,
            SUM(injured) as injured
        FROM incidents
        WHERE year >= '2015' AND year != ''
          AND month BETWEEN 1 AND 12
        GROUP BY year, month
        ORDER BY year, month
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 10. DAY-OF-WEEK PATTERN ──────────────────────────────────────────────────
def day_of_week_pattern() -> list:
    """
    Which days of the week record the most incidents and deaths.
    SQLite strftime('%w') returns 0=Sunday … 6=Saturday.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT
            CAST(strftime('%w', COALESCE(event_date, detected_at)) AS INTEGER) as dow,
            COUNT(*) as incidents,
            SUM(deaths) as deaths,
            SUM(injured) as injured
        FROM incidents
        WHERE event_date != '' OR detected_at != ''
        GROUP BY dow
        ORDER BY dow
    """).fetchall()
    conn.close()
    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    result = []
    dow_map = {r["dow"]: dict(r) for r in rows_to_list(rows)}
    for i, name in enumerate(days):
        d = dow_map.get(i, {"incidents":0,"deaths":0,"injured":0})
        result.append({
            "dow": i, "day": name,
            "incidents": d["incidents"],
            "deaths":    d["deaths"] or 0,
            "injured":   d["injured"] or 0,
        })
    return result

# ── 11. CASE FATALITY RATE BY TYPE ───────────────────────────────────────────
def case_fatality_rate() -> list:
    """
    For each incident type: deaths / (deaths + injured) × 100.
    Helps decision makers know which incident types are most lethal
    relative to the number of people affected.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT incident_type,
               COUNT(*) as incidents,
               SUM(deaths) as deaths,
               SUM(injured) as injured,
               SUM(deaths + injured) as total_affected
        FROM incidents
        WHERE deaths > 0 OR injured > 0
        GROUP BY incident_type
        ORDER BY deaths DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows_to_list(rows):
        affected = (r["total_affected"] or 0)
        cfr = round((r["deaths"] or 0) / affected * 100, 1) if affected > 0 else 0
        result.append({**r, "case_fatality_rate": cfr})
    result.sort(key=lambda x: x["case_fatality_rate"], reverse=True)
    return result

# ── 12. DEADLIEST INCIDENTS ───────────────────────────────────────────────────
def deadliest_incidents(limit=20) -> list:
    """Top incidents by death toll — for situational awareness."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, title, incident_type, district, province,
               deaths, injured, severity, event_date, source_name, source_url
        FROM incidents
        WHERE deaths > 0
        ORDER BY deaths DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 13. YEAR-OVER-YEAR COMPARISON ────────────────────────────────────────────
def year_over_year() -> list:
    """
    Compare each year against the previous year.
    Returns % change in incidents and deaths — useful for trend reporting.
    """
    yearly = yearly_trend()
    result = []
    for i, row in enumerate(yearly):
        prev = yearly[i-1] if i > 0 else None
        inc_change = None
        dth_change = None
        if prev and prev["incidents"] and prev["incidents"] > 0:
            inc_change = round((row["incidents"] - prev["incidents"]) / prev["incidents"] * 100, 1)
        if prev and prev["deaths"] and prev["deaths"] > 0:
            dth_change = round(((row["deaths"] or 0) - (prev["deaths"] or 0)) / prev["deaths"] * 100, 1)
        result.append({
            **row,
            "prev_incidents":  prev["incidents"] if prev else None,
            "prev_deaths":     prev["deaths"]    if prev else None,
            "inc_pct_change":  inc_change,
            "dth_pct_change":  dth_change,
        })
    return result

# ── 14. PROVINCE COMPARISON OVER TIME ────────────────────────────────────────
def province_trend() -> list:
    """Deaths per province per year — for comparative analysis."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            province,
            substr(COALESCE(event_date, detected_at), 1, 4) as year,
            COUNT(*) as incidents,
            SUM(deaths) as deaths,
            SUM(injured) as injured
        FROM incidents
        WHERE province NOT IN ('', 'Unknown', 'Rwanda (unspecified)')
          AND substr(COALESCE(event_date, detected_at), 1, 4) >= '2015'
        GROUP BY province, year
        ORDER BY province, year
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 15. INCIDENT HOUR OF DAY (if time data available) ────────────────────────
def hour_of_day_pattern() -> list:
    """
    Which hours of day see the most incidents.
    Only useful if event_date contains time component — otherwise returns empty.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT
            CAST(substr(event_date, 12, 2) AS INTEGER) as hour,
            COUNT(*) as incidents,
            SUM(deaths) as deaths
        FROM incidents
        WHERE length(event_date) >= 13
          AND substr(event_date, 12, 2) BETWEEN '00' AND '23'
        GROUP BY hour
        ORDER BY hour
    """).fetchall()
    conn.close()
    return rows_to_list(rows)

# ── 16. PEAK MONTHS SUMMARY ──────────────────────────────────────────────────
def peak_months_summary() -> dict:
    """
    Identify the single highest-risk month, season, and day of week.
    Returns plain-language findings for the decision-support summary panel.
    """
    seasonal = seasonal_pattern()
    dow      = day_of_week_pattern()
    heatmap  = monthly_heatmap()

    findings = {}

    # Highest incident month
    if seasonal:
        peak = max(seasonal, key=lambda x: x["avg_incidents"])
        findings["peak_month"]         = peak["month_name"]
        findings["peak_month_avg_inc"] = peak["avg_incidents"]
        findings["peak_month_avg_dth"] = peak["avg_deaths"]

    # Lowest incident month
    if seasonal:
        low = min(seasonal, key=lambda x: x["avg_incidents"])
        findings["low_month"]          = low["month_name"]

    # Rainy season risk (Rwanda: Mar-May, Oct-Nov)
    rainy = [s for s in seasonal if s["month_num"] in [3,4,5,10,11]]
    dry   = [s for s in seasonal if s["month_num"] not in [3,4,5,10,11]]
    if rainy and dry:
        rainy_avg = sum(s["avg_incidents"] for s in rainy) / len(rainy)
        dry_avg   = sum(s["avg_incidents"] for s in dry)   / len(dry)
        findings["rainy_vs_dry_ratio"] = round(rainy_avg / dry_avg, 2) if dry_avg > 0 else 1.0
        findings["rainy_avg"]          = round(rainy_avg, 1)
        findings["dry_avg"]            = round(dry_avg, 1)

    # Peak day of week
    if dow:
        peak_day = max(dow, key=lambda x: x["incidents"])
        findings["peak_day"]           = peak_day["day"]
        findings["peak_day_incidents"] = peak_day["incidents"]

    # Worst single year
    yearly = yearly_trend()
    if yearly:
        worst_year = max(yearly, key=lambda x: x["deaths"] or 0)
        findings["worst_year"]         = worst_year["year"]
        findings["worst_year_deaths"]  = worst_year["deaths"] or 0

    # Total years of data
    if heatmap:
        years = sorted(set(r["year"] for r in heatmap))
        findings["years_of_data"]      = len(years)
        findings["data_from"]          = years[0] if years else ""
        findings["data_to"]            = years[-1] if years else ""

    return findings

# ── 17. SOURCE TIER BREAKDOWN ────────────────────────────────────────────────
def by_source_tier() -> list:
    """
    Distribution of incidents and deaths across the 3 source tiers.
    Critical for understanding data quality at a glance.
    """
    from source_registry import TIER_INFO
    conn = get_db()
    rows = conn.execute("""
        SELECT
            COALESCE(source_tier, 3) as tier,
            COUNT(*) as incidents,
            SUM(deaths)  as deaths,
            SUM(injured) as injured,
            COUNT(DISTINCT source_name) as unique_sources
        FROM incidents
        GROUP BY tier
        ORDER BY tier
    """).fetchall()
    conn.close()
    result = []
    for t in [1, 2, 3]:
        row = next((dict(r) for r in rows if r["tier"]==t), None)
        info = TIER_INFO[t]
        result.append({
            "tier":           t,
            "code":           info["code"],
            "label":          info["label"],
            "description":    info["description"],
            "credibility":    info["credibility"],
            "color":          info["color"],
            "incidents":      row["incidents"]      if row else 0,
            "deaths":         row["deaths"]         if row else 0,
            "injured":        row["injured"]        if row else 0,
            "unique_sources": row["unique_sources"] if row else 0,
        })
    return result

def sources_by_tier() -> dict:
    """
    Return all sources organized by tier with their incident counts.
    Returns: { tier_num: [ {source_name, incidents, deaths}, ... ] }
    """
    from source_registry import TIER_INFO
    conn = get_db()
    rows = conn.execute("""
        SELECT
            COALESCE(source_tier, 3) as tier,
            source_name,
            COUNT(*) as incidents,
            SUM(deaths) as deaths
        FROM incidents
        WHERE source_name != ''
        GROUP BY tier, source_name
        ORDER BY tier, deaths DESC
    """).fetchall()
    conn.close()
    grouped = {1: [], 2: [], 3: []}
    for r in rows:
        r = dict(r)
        t = r["tier"]
        if t in grouped:
            grouped[t].append({
                "source_name": r["source_name"],
                "incidents":   r["incidents"],
                "deaths":      r["deaths"] or 0,
            })
    return {
        "tiers": [
            {**TIER_INFO[t], "tier": t, "sources": grouped[t]}
            for t in [1, 2, 3]
        ]
    }
