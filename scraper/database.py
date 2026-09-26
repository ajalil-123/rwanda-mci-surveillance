"""
database.py — Postgres (Neon) access for the scraper jobs.

Connection string comes from DATABASE_URL (repo-root .env locally). Neon's pooled
or direct URL both work: automatic prepared statements are disabled so the
PgBouncer pooler is safe. The public API is unchanged from the SQLite
version, so scraper.py needs no edits.
"""
import os, re, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger("database")

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_conn: psycopg.Connection | None = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise EnvironmentError("DATABASE_URL is not set. Copy .env.example to .env at the repo root.")
    return url


def get_db() -> psycopg.Connection:
    """New transactional connection (caller commits and closes). Rows are dicts."""
    return psycopg.connect(_database_url(), row_factory=dict_row, prepare_threshold=None)


def _shared() -> psycopg.Connection:
    """Autocommit connection reused across helper calls — Neon connections are TLS, so reuse matters."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(_database_url(), row_factory=dict_row, autocommit=True, prepare_threshold=None)
    return _conn


def _execute(sql: str, params=None):
    """Run a statement on the shared connection, reconnecting once if Neon dropped it."""
    global _conn
    try:
        return _shared().execute(sql, params)
    except psycopg.OperationalError:
        logger.warning("Database connection lost — reconnecting")
        _conn = None
        return _shared().execute(sql, params)


def _utcnow_iso() -> str:
    # Naive ISO string, matching every existing detected_at value
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


# ── Words to exclude from semantic fingerprint ───────────────────────────────
# Standard stop words + common news source names + words that vary between
# reports of the same event (e.g. "oman", "observer", "bbc", "voice")
_STOP = {
    # English stop words
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","was","were","are","be","been","has","had","have",
    "it","its","this","that","these","those","after","before","during",
    "following","near","about","into","after","between","through","over",
    # MCI words that appear in ALL incident articles (too generic)
    "rwanda","rwandan","people","person","killed","dead","died","injured",
    "wounded","according","reported","said","say","told","news","report",
    "world","says","latest","breaking","update","official","statement",
    # Common source/publication name fragments
    "observer","voice","times","press","daily","post","herald","tribune",
    "monitor","gazette","standard","guardian","telegraph","mirror","star",
    "bbc","cnn","reuters","afp","aps","rba","rfi","aljazeera","france",
    "africa","africanews","allafrica","eastleigh","newvision","oman",
    "chimp","ktpress","igihe","newtimes","reliefweb","google",
    # Numbers as words
    "one","two","three","four","five","six","seven","eight","nine","ten",
}

def _keywords(title: str, n: int = 4) -> str:
    """
    Extract top n event-specific content words from title.
    Strips source names, stop words, and generic MCI vocabulary so that
    articles about the same event produce the same keyword set.
    """
    # Remove everything after a dash or pipe (usually source name)
    # e.g. "Two killed in crash - Oman Observer" → "Two killed in crash"
    title = title.split(" - ")[0].split(" | ")[0].split("–")[0]
    words = re.findall(r"[a-z]+", title.lower())
    content = [w for w in words if w not in _STOP and len(w) > 3]
    # Sort so word order doesn't affect the fingerprint
    unique = sorted(set(content))
    return " ".join(unique[:n])


def make_semantic_id(data: dict) -> str | None:
    """
    Build a fingerprint identical for articles about the same real-world event.

    Core insight: In Rwanda, having the same death count AND injured count
    AND incident type within a 3-day window is already highly specific.
    Road crashes with exactly 2 dead and 6 injured are rare enough that
    two articles sharing those numbers within 3 days are almost certainly
    the same event.

    Components:
      - date_bucket  : 3-day window to absorb reporting date drift
                       (Feb 22 and Feb 23 → same bucket)
      - deaths       : exact death count
      - injured      : exact injured count
      - inc_type     : broad incident category (road/flood/landslide/etc.)

    Keywords deliberately excluded — they vary too much across sources
    describing the same event ("caravan hits fans" vs "cycling race accident"
    vs "traffic incident" are all the same Tour du Rwanda crash).

    Only active for events with deaths>0 or injured>0.
    Zero-casualty records are never semantically grouped.
    """
    raw_date = (data.get("event_date") or data.get("published_at") or "")[:10]
    try:
        d = datetime.strptime(raw_date, "%Y-%m-%d")
        bucket_day = (d.day // 3) * 3
        date_bucket = f"{d.year}-{d.month:02d}-{bucket_day:02d}"
    except ValueError:
        date_bucket = raw_date or "unknown"

    deaths  = int(data.get("deaths")  or 0)
    injured = int(data.get("injured") or 0)

    # Broad incident type — prevents "other" vs "road_accident" from splitting same event
    # Also treat "other" as matching the dominant civilian type for the same date/casualty combo
    raw_type = (data.get("incident_type") or "other").strip()
    type_groups = {
        "road_accident":"road",  "flood":"flood",    "landslide":"landslide",
        "explosion":"explosion", "fire":"fire",       "stampede":"stampede",
        "outbreak":"outbreak",   "drowning":"drown",  "building_collapse":"collapse",
        "violence":"violence",   "other":"road",  # "other" treated as road for dedup
    }
    inc_type = type_groups.get(raw_type, "road")

    # Death count tolerance — bucket 1 and 2 together (early vs confirmed count)
    # Deliberately EXCLUDE injured count: it varies wildly between early and updated
    # reports of the same event (e.g. "1 dead" then "2 dead, 6 injured").
    # deaths + date_bucket + incident_type is specific enough for Rwanda.
    deaths_bucket = max(2, (deaths // 2) * 2) if deaths > 0 else 0

    # For zero-casualty events, no semantic grouping
    if deaths == 0 and injured == 0:
        return None

    fingerprint = f"{date_bucket}|{deaths_bucket}|{inc_type}"
    return hashlib.md5(fingerprint.encode()).hexdigest()


def init_db():
    """Create tables, indexes and the verified_incidents view (idempotent)."""
    _execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def source_id(url: str, title: str) -> str:
    return hashlib.md5(f"{url}|{title}".encode()).hexdigest()


def incident_exists(sid: str) -> bool:
    return _execute("SELECT 1 FROM incidents WHERE source_id = %s", (sid,)).fetchone() is not None


def semantic_duplicate_exists(sem_id: str | None) -> bool:
    """
    Returns True if we already have a record with the same semantic fingerprint.
    This catches same-event articles from different sources / outlets.
    Only applies when deaths > 0 OR injured > 0 (don't deduplicate zero-casualty
    records by semantics alone — they may be genuinely different warnings).
    """
    if not sem_id:
        return False
    return _execute("SELECT 1 FROM incidents WHERE semantic_id = %s", (sem_id,)).fetchone() is not None


def insert_incident(data: dict) -> bool:
    """
    Insert if not a duplicate. Returns True if new row was added.
    Dedup checks:
      1. semantic_id — same event from a different outlet
                       (only active when deaths>0 or injured>0)
      2. source_id  — exact URL+title match, enforced atomically by the
                       UNIQUE constraint (ON CONFLICT DO NOTHING)
    Source tier is auto-classified from source_name.
    """
    sid = data.get("source_id") or source_id(
        data.get("source_url",""), data.get("title","")
    )

    deaths  = int(data.get("deaths")  or 0)
    injured = int(data.get("injured") or 0)
    sem_id  = make_semantic_id(data) if (deaths > 0 or injured > 0) else None

    if sem_id and semantic_duplicate_exists(sem_id):
        return False

    # Classify source into tier 1, 2, or 3.
    # For aggregators (Google News, AllAfrica), extract the real publisher
    # from the title and classify that — and overwrite source_name with the
    # actual publisher so users see the real source.
    try:
        from source_registry import classify_from_title_and_source
        tier, effective_source = classify_from_title_and_source(
            data.get("title",""),
            data.get("source_name", "")
        )
        if effective_source and effective_source != data.get("source_name",""):
            data = {**data, "source_name": effective_source}
    except Exception:
        tier = 3

    cur = _execute("""
        INSERT INTO incidents
            (source_id, semantic_id, title, description, full_text,
             source_name, source_url, source_tier, media_type,
             location, district, province, latitude, longitude,
             severity, deaths, injured, missing, incident_type, status,
             detected_at, published_at, event_date,
             ai_summary, ai_confidence, is_historical, verified, rwanda_verified)
        VALUES
            (%(source_id)s, %(semantic_id)s, %(title)s, %(description)s, %(full_text)s,
             %(source_name)s, %(source_url)s, %(source_tier)s, %(media_type)s,
             %(location)s, %(district)s, %(province)s, %(latitude)s, %(longitude)s,
             %(severity)s, %(deaths)s, %(injured)s, %(missing)s, %(incident_type)s, %(status)s,
             %(detected_at)s, %(published_at)s, %(event_date)s,
             %(ai_summary)s, %(ai_confidence)s, %(is_historical)s, %(verified)s, %(rwanda_verified)s)
        ON CONFLICT (source_id) DO NOTHING
    """, {
        "source_id":    sid,
        "semantic_id":  sem_id,
        "title":        data.get("title",""),
        "description":  (data.get("description","") or "")[:600],
        "full_text":    (data.get("full_text","")    or "")[:2000],
        "source_name":  data.get("source_name",""),
        "source_url":   data.get("source_url",""),
        "source_tier":  tier,
        "media_type":   data.get("media_type","news_scrape"),
        "location":     data.get("location","Rwanda"),
        "district":     data.get("district",""),
        "province":     data.get("province",""),
        "latitude":     data.get("latitude"),
        "longitude":    data.get("longitude"),
        "severity":     int(data.get("severity") or 1),
        "deaths":       deaths,
        "injured":      injured,
        "missing":      int(data.get("missing") or 0),
        "incident_type":data.get("incident_type","other"),
        "status":       data.get("status","active"),
        "detected_at":  _utcnow_iso(),
        "published_at": data.get("published_at",""),
        "event_date":   data.get("event_date",""),
        "ai_summary":   data.get("ai_summary",""),
        "ai_confidence":float(data.get("ai_confidence") or 0.0),
        "is_historical":    1 if data.get("is_historical") else 0,
        "verified":         0,
        "rwanda_verified":  data.get("rwanda_verified"),  # None/1/0
    })
    return cur.rowcount == 1


def log_scrape(source, scrape_type, started_at, finished_at, seen, added, error=None):
    _execute("""
        INSERT INTO scrape_log (source, scrape_type, started_at, finished_at,
                                articles_seen, incidents_added, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (source, scrape_type, started_at, finished_at, seen, added, error))


def get_cursor(source):
    return _execute("SELECT * FROM scrape_cursor WHERE source = %s", (source,)).fetchone()


def set_cursor(source, last_url="", last_date="", page=1):
    _execute("""
        INSERT INTO scrape_cursor (source, last_url, last_date, page)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (source) DO UPDATE SET last_url = excluded.last_url,
            last_date = excluded.last_date, page = excluded.page
    """, (source, last_url, last_date, page))
