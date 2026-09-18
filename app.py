"""
app.py — Flask backend for Rwanda MCI Surveillance System
Works locally (Windows/Mac/Linux) and on Render.com
"""
# Load .env file if present (local development)
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — set env vars manually

import os, json, threading, time, logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_from_directory, request

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# On Render, use /tmp for writable storage (persists within a session).
# For permanent persistence, mount a Render Disk at /data.
# Locally, use the project folder.
if os.path.exists("/tmp") and os.environ.get("RENDER"):
    DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
    LOG_DIR  = "/tmp/logs"
else:
    DATA_DIR = os.path.join(BASE_DIR, "data")
    LOG_DIR  = os.path.join(BASE_DIR, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR,  exist_ok=True)

# Inject paths into database module before importing
os.environ.setdefault("MCI_DATA_DIR", DATA_DIR)
os.environ.setdefault("MCI_LOG_DIR",  LOG_DIR)

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "system.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("app")

# ── app ───────────────────────────────────────────────────────────────────────
# Use the directory containing this file — works correctly under gunicorn on Render
APP_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=APP_DIR, template_folder=APP_DIR)

try:
    from flask_cors import CORS; CORS(app)
except ImportError:
    pass

# ── local modules ─────────────────────────────────────────────────────────────
from database import init_db, get_db
from scraper  import run_historical_scrape, run_incremental_scrape
from analytics import (
    get_summary_stats, by_incident_type, district_hotspots,
    monthly_trend, yearly_trend, seasonal_pattern, type_trend_by_year,
    predict_next_month, high_risk_districts,
    recent_incidents, all_mapped_incidents, scrape_status,
    monthly_heatmap, day_of_week_pattern, case_fatality_rate,
    deadliest_incidents, year_over_year, province_trend,
    hour_of_day_pattern, peak_months_summary,
    by_source_tier, sources_by_tier,
    # MCI classification
    mci_summary_stats, mci_by_type, mci_hotspots,
    mci_monthly_trend, mci_yearly_trend,
    mci_incidents, non_mci_incidents,
)

# ── background scheduler ──────────────────────────────────────────────────────
_scheduler_running = False
_historical_done   = False
_last_incremental  = None
_scrape_lock       = threading.Lock()

def scheduler():
    global _scheduler_running, _historical_done, _last_incremental
    _scheduler_running = True
    logger.info("Scheduler started.")

    # ── Step 1: historical scrape (runs once per DB) ──────────────────────
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    conn.close()

    if count == 0:
        logger.info("Empty database — running historical scrape first.")
        with _scrape_lock:
            run_historical_scrape()
        _historical_done = True
    else:
        logger.info(f"Database has {count} incidents — skipping historical scrape.")
        _historical_done = True

    # ── Step 2: incremental refresh every 30 minutes ─────────────────────
    while _scheduler_running:
        logger.info("Running incremental refresh...")
        with _scrape_lock:
            run_incremental_scrape()
        _last_incremental = datetime.utcnow().isoformat()
        logger.info("Incremental refresh done. Next run in 30 minutes.")
        time.sleep(1800)

# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(APP_DIR, "index.html")

# Dashboard stats
@app.route("/api/stats")
def api_stats():
    return jsonify(get_summary_stats())

# All incidents for map
@app.route("/api/incidents/map")
def api_map():
    min_deaths = int(request.args.get("min_deaths", 0))
    return jsonify(all_mapped_incidents(min_deaths))

# Recent incident feed
@app.route("/api/incidents/recent")
def api_recent():
    hours      = int(request.args.get("hours", 72))
    min_sev    = int(request.args.get("min_severity", 1))
    return jsonify(recent_incidents(hours, min_sev))

# Single incident
@app.route("/api/incidents/<int:iid>")
def api_incident(iid):
    conn = get_db()
    row  = conn.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
    conn.close()
    return jsonify(dict(row)) if row else (jsonify({"error": "Not found"}), 404)

# Resolve / reopen
@app.route("/api/incidents/<int:iid>/status", methods=["POST"])
def api_set_status(iid):
    status = request.json.get("status","resolved")
    conn   = get_db()
    conn.execute("UPDATE incidents SET status=? WHERE id=?", (status, iid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# Analytics
@app.route("/api/analytics/types")
def api_types():
    return jsonify(by_incident_type())

@app.route("/api/analytics/hotspots")
def api_hotspots():
    return jsonify(district_hotspots())

@app.route("/api/analytics/monthly")
def api_monthly():
    years = int(request.args.get("years", 5))
    return jsonify(monthly_trend(years))

@app.route("/api/analytics/yearly")
def api_yearly():
    return jsonify(yearly_trend())

@app.route("/api/analytics/seasonal")
def api_seasonal():
    return jsonify(seasonal_pattern())

@app.route("/api/analytics/type-trend")
def api_type_trend():
    return jsonify(type_trend_by_year())

@app.route("/api/analytics/heatmap")
def api_heatmap():
    return jsonify(monthly_heatmap())

@app.route("/api/analytics/dow")
def api_dow():
    return jsonify(day_of_week_pattern())

@app.route("/api/analytics/cfr")
def api_cfr():
    return jsonify(case_fatality_rate())

@app.route("/api/analytics/deadliest")
def api_deadliest():
    limit = int(request.args.get("limit", 20))
    return jsonify(deadliest_incidents(limit))

@app.route("/api/analytics/yoy")
def api_yoy():
    return jsonify(year_over_year())

@app.route("/api/analytics/province-trend")
def api_province_trend():
    return jsonify(province_trend())

@app.route("/api/analytics/peak-months")
def api_peak_months():
    return jsonify(peak_months_summary())

@app.route("/api/analytics/source-tiers")
def api_source_tiers():
    return jsonify(by_source_tier())

@app.route("/api/analytics/sources-by-tier")
def api_sources_by_tier():
    return jsonify(sources_by_tier())

# Predictions
@app.route("/api/predictions/next-month")
def api_predict_month():
    return jsonify(predict_next_month())

@app.route("/api/predictions/risk-districts")
def api_risk_districts():
    return jsonify(high_risk_districts())

# Scraper control
@app.route("/api/scraper/status")
def api_scraper_status():
    conn  = get_db()
    total = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    hist  = conn.execute("SELECT COUNT(*) FROM incidents WHERE is_historical=1").fetchone()[0]
    conn.close()
    return jsonify({
        "scheduler_running":   _scheduler_running,
        "historical_complete": _historical_done,
        "last_incremental":    _last_incremental,
        "total_incidents":     total,
        "historical_incidents":hist,
        "scrape_log":          scrape_status()[:10],
    })

@app.route("/api/scraper/refresh", methods=["POST"])
def api_manual_refresh():
    """Manually trigger an incremental refresh."""
    if _scrape_lock.locked():
        return jsonify({"ok": False, "message": "Scrape already running"}), 429
    def do():
        with _scrape_lock:
            run_incremental_scrape()
    threading.Thread(target=do, daemon=True).start()
    return jsonify({"ok": True, "message": "Incremental refresh started"})

@app.route("/api/scraper/historical", methods=["POST"])
def api_manual_historical():
    """Re-run full historical scrape (admin use)."""
    if _scrape_lock.locked():
        return jsonify({"ok": False, "message": "Scrape already running"}), 429
    def do():
        with _scrape_lock:
            run_historical_scrape()
    threading.Thread(target=do, daemon=True).start()
    return jsonify({"ok": True, "message": "Historical scrape started"})

# ── Data Explorer ─────────────────────────────────────────────────────────────
@app.route("/api/data/all")
def api_data_all():
    """Return all incidents for the Data Explorer table."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, event_date, detected_at, title, incident_type,
               district, province, latitude, longitude,
               deaths, injured, missing, severity,
               source_name, source_url, source_tier, media_type,
               ai_summary, ai_confidence, status, is_historical
        FROM incidents
        ORDER BY COALESCE(event_date, detected_at) DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── Exports ───────────────────────────────────────────────────────────────────
@app.route("/api/export/csv")
def api_export_csv():
    """Download all incidents as CSV (filtered by query params)."""
    import csv, io
    rows = _filtered_rows(request.args)
    si   = io.StringIO()
    cols = ["id","event_date","title","incident_type","district","province",
            "deaths","injured","missing","severity","source_name","source_tier",
            "source_url","media_type","detected_at","ai_summary"]
    writer = csv.DictWriter(si, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output = si.getvalue()
    from flask import Response
    return Response(
        "\ufeff" + output,          # BOM for Excel UTF-8
        mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=rwanda_mci_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@app.route("/api/export/excel")
def api_export_excel():
    """Download incidents as Excel .xlsx file."""
    import io
    rows = _filtered_rows(request.args)
    from flask import Response

    # Build Excel manually using openpyxl if available, else fall back to CSV
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Rwanda MCI Incidents"

        cols = ["id","event_date","title","incident_type","district","province",
                "deaths","injured","missing","severity","source_name","source_tier",
                "source_url","media_type","detected_at","ai_summary"]
        headers = ["ID","Date","Title","Type","District","Province",
                   "Deaths","Injured","Missing","Severity","Source","Tier",
                   "URL","Media","Detected At","AI Summary"]

        # header row styling
        header_fill = PatternFill("solid", fgColor="0D1117")
        for ci, (col, hdr) in enumerate(zip(cols, headers), 1):
            cell = ws.cell(row=1, column=ci, value=hdr)
            cell.font      = Font(bold=True, color="58A6FF", name="Calibri", size=10)
            cell.fill      = header_fill
            cell.alignment = Alignment(horizontal="center")

        # severity colours
        sev_colours = {1:"3FB950",2:"D29922",3:"DB6D28",4:"F85149",5:"BC8CFF"}

        for ri, row in enumerate(rows, 2):
            for ci, col in enumerate(cols, 1):
                val  = row.get(col, "")
                cell = ws.cell(row=ri, column=ci, value=val)
                cell.font = Font(name="Calibri", size=9)
                if col == "deaths" and (val or 0) > 0:
                    cell.font = Font(name="Calibri", size=9, bold=True, color="F85149")
                if col == "severity":
                    sev_col = sev_colours.get(val, "484F58")
                    cell.fill = PatternFill("solid", fgColor=sev_col)

        # column widths
        widths = [5,12,55,16,14,12,7,7,7,5,22,5,40,12,18,60]
        for ci, w in enumerate(widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w

        ws.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(
            buf.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition":
                     f"attachment; filename=rwanda_mci_{datetime.now().strftime('%Y%m%d')}.xlsx"}
        )

    except ImportError:
        # openpyxl not installed — redirect to CSV
        return api_export_csv()

def _filtered_rows(args):
    """Apply Data Explorer filters and return list of dicts."""
    q      = args.get("q","").lower()
    type_  = args.get("type","")
    prov   = args.get("province","")
    year   = args.get("year","")
    mind   = int(args.get("min_deaths",0) or 0)

    conn   = get_db()
    rows   = conn.execute("""
        SELECT id, event_date, detected_at, title, incident_type,
               district, province, deaths, injured, missing, severity,
               source_name, source_url, media_type, ai_summary
        FROM incidents
        ORDER BY COALESCE(event_date, detected_at) DESC
    """).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        text = f"{d.get('title','')} {d.get('district','')} {d.get('province','')} {d.get('incident_type','')} {d.get('source_name','')}".lower()
        dy   = (d.get("event_date") or d.get("detected_at") or "")[:4]
        if q    and q    not in text:       continue
        if type_ and d.get("incident_type") != type_: continue
        if prov  and d.get("province")      != prov:  continue
        if year  and dy                     != year:  continue
        if (d.get("deaths") or 0) < mind:             continue
        result.append(d)
    return result

# ── MCI CLASSIFICATION ROUTES ─────────────────────────────────────────────────

@app.route("/api/mci/stats")
def api_mci_stats():
    """MCI vs non-MCI split: counts, deaths, injured, worst event."""
    return jsonify(mci_summary_stats())

@app.route("/api/mci/types")
def api_mci_types():
    """Incident type breakdown for MCIs only (deaths ≥ 3)."""
    return jsonify(mci_by_type())

@app.route("/api/mci/hotspots")
def api_mci_hotspots():
    """District hotspots restricted to MCI events."""
    return jsonify(mci_hotspots())

@app.route("/api/mci/monthly")
def api_mci_monthly():
    years = int(request.args.get("years", 5))
    return jsonify(mci_monthly_trend(years))

@app.route("/api/mci/yearly")
def api_mci_yearly():
    return jsonify(mci_yearly_trend())

@app.route("/api/mci/incidents")
def api_mci_incidents():
    """Paginated list of MCI incidents (deaths ≥ 3)."""
    limit  = int(request.args.get("limit",  200))
    offset = int(request.args.get("offset", 0))
    return jsonify(mci_incidents(limit, offset))

@app.route("/api/non-mci/incidents")
def api_non_mci_incidents():
    """Paginated list of non-MCI incidents (deaths < 3)."""
    limit  = int(request.args.get("limit",  200))
    offset = int(request.args.get("offset", 0))
    return jsonify(non_mci_incidents(limit, offset))


# ── CLAUDE AI ROUTES ──────────────────────────────────────────────────────────

@app.route("/api/ai/summarize/<int:iid>", methods=["POST"])
def api_ai_summarize(iid):
    """Generate/refresh Claude AI summary for a single incident."""
    force = (request.json or {}).get("force", False)
    conn  = get_db()
    row   = conn.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Incident not found"}), 404
    inc = dict(row)
    if inc.get("ai_summary") and not force:
        return jsonify({"summary": inc["ai_summary"], "confidence": inc.get("ai_confidence", 0.0), "flags": [], "cached": True})
    try:
        from claude_ai import summarize_incident
        result = summarize_incident(inc)
    except (ImportError, EnvironmentError) as exc:
        return jsonify({"error": str(exc)}), 503
    if result.get("summary"):
        conn = get_db()
        conn.execute("UPDATE incidents SET ai_summary=?, ai_confidence=? WHERE id=?",
                     (result["summary"], result["confidence"], iid))
        conn.commit()
        conn.close()
    return jsonify(result)


@app.route("/api/ai/data-quality")
def api_ai_data_quality():
    """Run Claude data-quality analysis on recent incidents."""
    days     = int(request.args.get("days", 90))
    mci_only = request.args.get("mci_only", "0") == "1"
    cutoff   = (datetime.utcnow() - timedelta(days=days)).isoformat()
    where    = "detected_at >= ?"
    params   = [cutoff]
    if mci_only:
        where += " AND deaths >= 3"
    conn = get_db()
    rows = conn.execute(f"""
        SELECT id, title, event_date, detected_at, incident_type, district,
               province, deaths, injured, missing, source_name, ai_summary
        FROM incidents WHERE {where} ORDER BY detected_at DESC
    """, params).fetchall()
    conn.close()
    try:
        from claude_ai import data_quality_report
        return jsonify(data_quality_report([dict(r) for r in rows]))
    except (ImportError, EnvironmentError) as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/ai/narrative")
def api_ai_narrative():
    """Generate Claude MCI surveillance narrative for a period."""
    days   = int(request.args.get("days", 30))
    label  = request.args.get("label", f"Last {days} days")
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()[:10]
    conn   = get_db()
    rows   = conn.execute("""
        SELECT id, event_date, title, incident_type, district, province,
               deaths, injured, missing, source_name
        FROM incidents WHERE deaths >= 3
          AND COALESCE(event_date, detected_at) >= ?
        ORDER BY deaths DESC
    """, (cutoff,)).fetchall()
    conn.close()
    try:
        from claude_ai import mci_narrative
        return jsonify(mci_narrative([dict(r) for r in rows], label))
    except (ImportError, EnvironmentError) as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/ai/batch-summarize", methods=["POST"])
def api_ai_batch_summarize():
    """Queue AI summaries for incidents without one (background thread)."""
    body     = request.json or {}
    limit    = int(body.get("limit", 50))
    mci_only = bool(body.get("mci_only", False))
    where    = "(ai_summary IS NULL OR ai_summary = '')"
    if mci_only:
        where += " AND deaths >= 3"
    conn = get_db()
    rows = conn.execute(
        f"SELECT id FROM incidents WHERE {where} ORDER BY deaths DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    ids = [r["id"] for r in rows]
    if not ids:
        return jsonify({"ok": True, "message": "No incidents need summarizing", "queued": 0})
    def _do_batch():
        try:
            from claude_ai import summarize_incident
        except (ImportError, EnvironmentError) as exc:
            logger.error("batch-summarize: %s", exc)
            return
        for iid in ids:
            try:
                conn = get_db()
                row  = conn.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
                conn.close()
                if not row:
                    continue
                result = summarize_incident(dict(row))
                if result.get("summary"):
                    conn = get_db()
                    conn.execute("UPDATE incidents SET ai_summary=?, ai_confidence=? WHERE id=?",
                                 (result["summary"], result["confidence"], iid))
                    conn.commit()
                    conn.close()
            except Exception as exc:
                logger.warning("batch-summarize incident %d: %s", iid, exc)
    threading.Thread(target=_do_batch, daemon=True).start()
    return jsonify({"ok": True, "queued": len(ids), "message": f"Summarizing {len(ids)} incidents in background"})


@app.route("/api/ai/batch-verify-rwanda", methods=["POST"])
def api_batch_verify_rwanda():
    """
    Re-verify Rwanda relevance for existing incidents using Claude.
    POST body: optional {"limit": 100, "unverified_only": true}
      unverified_only=true  → only incidents where rwanda_verified IS NULL
      unverified_only=false → re-check ALL incidents (admin use)
    Runs asynchronously. Check /api/scraper/status for DB counts.
    """
    body           = request.json or {}
    limit          = int(body.get("limit", 100))
    unverified_only = bool(body.get("unverified_only", True))

    where = "rwanda_verified IS NULL" if unverified_only else "1=1"
    conn  = get_db()
    rows  = conn.execute(
        f"SELECT id, title, description, full_text, source_name, source_url, district, province "
        f"FROM incidents WHERE {where} ORDER BY deaths DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    ids = [r["id"] for r in rows]
    incidents_data = [dict(r) for r in rows]

    if not ids:
        return jsonify({"ok": True, "message": "No incidents need verification", "queued": 0})

    def _do_verify():
        try:
            from claude_ai import verify_rwanda_relevance
        except (ImportError, EnvironmentError) as exc:
            logger.error("batch-verify-rwanda: %s", exc)
            return
        kept = rejected = 0
        for inc in incidents_data:
            try:
                result = verify_rwanda_relevance(inc)
                verified = 1 if result["is_rwanda"] else 0
                conn = get_db()
                conn.execute("UPDATE incidents SET rwanda_verified=? WHERE id=?", (verified, inc["id"]))
                conn.commit()
                conn.close()
                if verified:
                    kept += 1
                else:
                    rejected += 1
                    logger.info("Batch verify — rejected: %s | %s", inc.get("title","")[:60], result.get("reason",""))
            except Exception as exc:
                logger.warning("batch-verify incident %s: %s", inc.get("id"), exc)
        logger.info("Batch Rwanda verify complete: %d kept, %d rejected", kept, rejected)

    threading.Thread(target=_do_verify, daemon=True).start()
    return jsonify({
        "ok":     True,
        "queued": len(ids),
        "message": f"Verifying {len(ids)} incidents in background — rejected ones will disappear from the dashboard automatically.",
    })


@app.route("/api/ai/batch-reclassify", methods=["POST"])
def api_ai_batch_reclassify():
    """
    Reclassify incidents whose type is 'other' or NULL using Claude.
    POST body: optional {"limit": 100}
    Runs asynchronously in a background thread.
    """
    body  = request.json or {}
    limit = int(body.get("limit", 100))

    conn = get_db()
    rows = conn.execute(
        """SELECT id, title, description, full_text, source_name, source_url,
                  district, province, incident_type
           FROM incidents
           WHERE incident_type IS NULL OR incident_type = '' OR incident_type = 'other'
           ORDER BY deaths DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"ok": True, "message": "No unclassified incidents found", "queued": 0})

    incidents_data = [dict(r) for r in rows]

    _VALID_TYPES = {
        "road_accident", "flood", "landslide", "explosion", "fire",
        "stampede", "outbreak", "drowning", "building_collapse", "violence",
    }

    def _do_reclassify():
        try:
            from claude_ai import verify_rwanda_relevance
        except (ImportError, EnvironmentError) as exc:
            logger.error("batch-reclassify: %s", exc)
            return
        updated = deleted = 0
        for inc in incidents_data:
            try:
                result = verify_rwanda_relevance(inc)
                new_type = result.get("incident_type", "other")
                conn = get_db()
                if new_type and new_type in _VALID_TYPES:
                    conn.execute(
                        "UPDATE incidents SET incident_type=? WHERE id=?",
                        (new_type, inc["id"])
                    )
                    logger.info("Reclassified #%s → %s | %s", inc["id"], new_type, inc.get("title","")[:60])
                    updated += 1
                else:
                    # Claude still can't classify — delete the record
                    conn.execute("DELETE FROM incidents WHERE id=?", (inc["id"],))
                    logger.info("Deleted unclassifiable #%s: %s", inc["id"], inc.get("title","")[:60])
                    deleted += 1
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning("batch-reclassify incident %s: %s", inc.get("id"), exc)
        logger.info("Batch reclassify complete: %d updated, %d deleted", updated, deleted)

    threading.Thread(target=_do_reclassify, daemon=True).start()
    return jsonify({
        "ok":     True,
        "queued": len(incidents_data),
        "message": f"Reclassifying {len(incidents_data)} untyped incidents — anything Claude can't classify will be deleted. Refresh when done.",
    })


@app.route("/api/admin/delete-unclassified", methods=["POST"])
def api_delete_unclassified():
    """Immediately delete all incidents with incident_type='other', NULL, or empty."""
    conn = get_db()
    result = conn.execute(
        "DELETE FROM incidents WHERE incident_type IS NULL OR incident_type = '' OR incident_type = 'other'"
    )
    deleted = result.rowcount
    conn.commit()
    conn.close()
    logger.info("Deleted %d unclassified incidents", deleted)
    return jsonify({"ok": True, "deleted": deleted, "message": f"Deleted {deleted} unclassified incidents."})


# ── module-level initialisation (runs under gunicorn too) ─────────────────────
# Create database schema and start background scheduler when the module is
# imported. This ensures gunicorn workers have a working DB before serving
# any requests. Guarded with a flag so it only runs once even with --preload.
_INITIALISED = False

def _auto_reclassify():
    """
    On startup, silently reclassify any incidents still typed as 'other'.
    Runs in a background thread so it never delays the first request.
    Incidents Claude can't classify get deleted.
    Only runs when ANTHROPIC_API_KEY is present.
    """
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        from claude_ai import verify_rwanda_relevance
    except Exception:
        return

    _VALID_TYPES = {
        "road_accident", "flood", "landslide", "explosion", "fire",
        "stampede", "outbreak", "drowning", "building_collapse", "violence",
    }

    conn = get_db()
    rows = conn.execute(
        """SELECT id, title, description, full_text, source_name, source_url,
                  district, province, incident_type
           FROM incidents
           WHERE incident_type IS NULL OR incident_type = '' OR incident_type = 'other'
           ORDER BY deaths DESC"""
    ).fetchall()
    conn.close()

    if not rows:
        return

    logger.info("Auto-reclassify: %d unclassified incidents found", len(rows))
    updated = deleted = 0
    for row in rows:
        inc = dict(row)
        try:
            result = verify_rwanda_relevance(inc)
            new_type = result.get("incident_type", "other")
            conn = get_db()
            if new_type and new_type in _VALID_TYPES:
                conn.execute("UPDATE incidents SET incident_type=? WHERE id=?", (new_type, inc["id"]))
                updated += 1
                logger.info("Auto-reclassify #%s → %s", inc["id"], new_type)
            else:
                conn.execute("DELETE FROM incidents WHERE id=?", (inc["id"],))
                deleted += 1
                logger.info("Auto-reclassify deleted #%s (unclassifiable): %s", inc["id"], inc.get("title","")[:60])
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Auto-reclassify #%s failed: %s", inc.get("id"), exc)

    logger.info("Auto-reclassify complete: %d classified, %d deleted", updated, deleted)


def _purge_animal_records():
    """
    On startup, delete any incidents that are about animal casualties only,
    not human. Uses keyword matching on title — no Claude API needed.
    Catches records like 'swine fever kills 60 pigs' that slip through
    as 'outbreak' before Claude's human-only filter was in place.
    """
    ANIMAL_PATTERNS = [
        "%swine fever%", "%swine flu%", "%african swine%", "% asf %",
        "%pig%died%", "%pig%dead%", "%pig%kill%", "%pigs %died%",
        "%poultry%died%", "%poultry%dead%", "%poultry%kill%",
        "%bird flu%", "%avian flu%", "%avian influenza%",
        "%cattle disease%", "%cattle died%", "%cattle dead%",
        "%livestock disease%", "%livestock died%", "%livestock dead%",
        "%foot-and-mouth%", "%foot and mouth%",
        "%animal quarantine%", "%pig trade%", "%pig ban%",
        "%veterinary%died%", "%chicken%died%", "%hen%died%",
    ]
    conn = get_db()
    deleted = 0
    for pat in ANIMAL_PATTERNS:
        result = conn.execute(
            "DELETE FROM incidents WHERE LOWER(title) LIKE ?", (pat,)
        )
        deleted += result.rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info("Animal-record purge: deleted %d non-human incident(s)", deleted)


def _re_enrich_casualties():
    """
    Re-extract deaths/injured counts for all existing records using the current
    (fixed) extract_deaths / extract_injured functions from nlp.py.

    Runs synchronously on startup so the corrected numbers are available
    immediately. Safe to re-run repeatedly — only writes when a value changes.
    Fixes cases like "Four sand miners killed" → deaths was 1, now corrected to 4.
    """
    try:
        from nlp import extract_deaths, extract_injured
        from database import make_semantic_id
    except Exception as exc:
        logger.warning("_re_enrich_casualties: import failed — %s", exc)
        return

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, description, deaths, injured, incident_type, event_date, district FROM incidents"
        ).fetchall()
        updated = 0
        for row in rows:
            text = f"{row['title'] or ''} {row['description'] or ''}"
            new_d = extract_deaths(text)
            new_i = extract_injured(text)
            if new_d != (row["deaths"] or 0) or new_i != (row["injured"] or 0):
                # Recompute semantic_id with corrected casualty figures
                new_sem = make_semantic_id({
                    "deaths":        new_d,
                    "injured":       new_i,
                    "incident_type": row["incident_type"],
                    "event_date":    row["event_date"],
                    "district":      row["district"],
                })
                conn.execute(
                    "UPDATE incidents SET deaths=?, injured=?, semantic_id=? WHERE id=?",
                    (new_d, new_i, new_sem, row["id"]),
                )
                updated += 1
        conn.commit()
        if updated:
            logger.info("Casualty re-enrichment: corrected %d record(s)", updated)
    except Exception as exc:
        logger.warning("_re_enrich_casualties failed: %s", exc)
    finally:
        conn.close()


def _purge_violence_records():
    """
    Delete all violence-typed incidents and genocide/commemoration articles.
    Violence is out of scope for this public-health accident/disaster system.
    Runs synchronously on startup so the dashboard is clean immediately.
    """
    conn = get_db()
    deleted = 0

    # All records classified as 'violence'
    r = conn.execute("DELETE FROM incidents WHERE incident_type = 'violence'")
    deleted += r.rowcount

    # Genocide commemoration articles that slipped through as other types
    GENOCIDE_PATTERNS = [
        "%genocide%remember%",
        "%genocide%commemor%",
        "%genocide%annivers%",
        "%genocide%memorial%",
        "%genocide at %",            # "Genocide at 32", "Genocide at 30"
        "%world remembers%killed%",
        "%remembrance%genocide%",
        "%kwibuka%",                 # Kinyarwanda genocide memorial campaign
        "%100 days%killed%",
        "%100-day%killing%",
    ]
    for pat in GENOCIDE_PATTERNS:
        r = conn.execute(
            "DELETE FROM incidents WHERE LOWER(title) LIKE ?", (pat,)
        )
        deleted += r.rowcount

    conn.commit()
    conn.close()
    if deleted:
        logger.info("Violence/genocide purge: deleted %d incident(s)", deleted)


def _initialise():
    global _INITIALISED
    if _INITIALISED:
        return
    init_db()
    _purge_animal_records()           # instant keyword purge — runs synchronously
    _purge_violence_records()         # remove violence/genocide records — runs synchronously
    _re_enrich_casualties()           # fix death/injured counts — runs synchronously
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=_auto_reclassify, daemon=True).start()
    _INITIALISED = True
    logger.info("Database initialised and scheduler started.")

_initialise()

# ── entry point (only used when running `python app.py` directly) ─────────────
if __name__ == "__main__":
    logger.info("Server starting on http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)