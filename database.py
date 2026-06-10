"""
database.py — SQLite schema, init, and helpers.

Deduplication strategy (two layers):
  1. source_id  — hash(url+title): exact URL dedup (same article, same source)
  2. semantic_id — hash(date_window+deaths+injured+type+keywords): same EVENT,
                   different sources. Prevents storing 6 articles about the
                   same Tour du Rwanda crash from 6 different news outlets.
"""
import os, sqlite3, re, hashlib, json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "mci_rwanda.db")

os.makedirs(DATA_DIR, exist_ok=True)

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT UNIQUE,
    semantic_id     TEXT,
    title           TEXT NOT NULL,
    description     TEXT,
    full_text       TEXT,
    source_name     TEXT,
    source_url      TEXT,
    media_type      TEXT,
    location        TEXT,
    district        TEXT,
    province        TEXT,
    latitude        REAL,
    longitude       REAL,
    severity        INTEGER DEFAULT 1,
    deaths          INTEGER DEFAULT 0,
    injured         INTEGER DEFAULT 0,
    missing         INTEGER DEFAULT 0,
    incident_type   TEXT,
    status          TEXT DEFAULT 'active',
    detected_at     TEXT NOT NULL,
    published_at    TEXT,
    event_date      TEXT,
    ai_summary      TEXT,
    ai_confidence   REAL DEFAULT 0.0,
    is_historical   INTEGER DEFAULT 0,
    verified        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source           TEXT,
    scrape_type      TEXT,
    started_at       TEXT,
    finished_at      TEXT,
    articles_seen    INTEGER DEFAULT 0,
    incidents_added  INTEGER DEFAULT 0,
    error            TEXT
);

CREATE TABLE IF NOT EXISTS scrape_cursor (
    source    TEXT PRIMARY KEY,
    last_url  TEXT,
    last_date TEXT,
    page      INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_incidents_event_date  ON incidents(event_date);
CREATE INDEX IF NOT EXISTS idx_incidents_district    ON incidents(district);
CREATE INDEX IF NOT EXISTS idx_incidents_type        ON incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_incidents_detected    ON incidents(detected_at);
CREATE INDEX IF NOT EXISTS idx_incidents_deaths      ON incidents(deaths);
CREATE INDEX IF NOT EXISTS idx_incidents_semantic    ON incidents(semantic_id);
"""

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


def make_semantic_id(data: dict) -> str:
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
    except:
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
    conn = get_db()
    conn.executescript(SCHEMA)
    # Add semantic_id column to existing databases that don't have it yet
    try:
        conn.execute("ALTER TABLE incidents ADD COLUMN semantic_id TEXT")
        conn.commit()
    except:
        pass  # column already exists
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def source_id(url: str, title: str) -> str:
    return hashlib.md5(f"{url}|{title}".encode()).hexdigest()


def incident_exists(sid: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT 1 FROM incidents WHERE source_id=?", (sid,)).fetchone()
    conn.close()
    return row is not None


def semantic_duplicate_exists(sem_id: str) -> bool:
    """
    Returns True if we already have a record with the same semantic fingerprint.
    This catches same-event articles from different sources / outlets.
    Only applies when deaths > 0 OR injured > 0 (don't deduplicate zero-casualty
    records by semantics alone — they may be genuinely different warnings).
    """
    if not sem_id:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM incidents WHERE semantic_id=?", (sem_id,)
    ).fetchone()
    conn.close()
    return row is not None


def insert_incident(data: dict) -> bool:
    """
    Insert if not a duplicate. Returns True if new row was added.
    Dedup checks (in order):
      1. source_id  — exact URL+title match
      2. semantic_id — same event from a different outlet
                       (only active when deaths>0 or injured>0)
    """
    sid = data.get("source_id") or source_id(
        data.get("source_url",""), data.get("title","")
    )

    # Layer 1: exact dedup
    if incident_exists(sid):
        return False

    # Layer 2: semantic dedup (only for casualty events)
    deaths  = int(data.get("deaths")  or 0)
    injured = int(data.get("injured") or 0)
    sem_id  = make_semantic_id(data) if (deaths > 0 or injured > 0) else None

    if sem_id and semantic_duplicate_exists(sem_id):
        return False

    conn = get_db()
    conn.execute("""
        INSERT OR IGNORE INTO incidents
            (source_id, semantic_id, title, description, full_text,
             source_name, source_url, media_type,
             location, district, province, latitude, longitude,
             severity, deaths, injured, missing, incident_type, status,
             detected_at, published_at, event_date,
             ai_summary, ai_confidence, is_historical, verified)
        VALUES
            (:source_id,:semantic_id,:title,:description,:full_text,
             :source_name,:source_url,:media_type,
             :location,:district,:province,:latitude,:longitude,
             :severity,:deaths,:injured,:missing,:incident_type,:status,
             :detected_at,:published_at,:event_date,
             :ai_summary,:ai_confidence,:is_historical,:verified)
    """, {
        "source_id":    sid,
        "semantic_id":  sem_id,
        "title":        data.get("title",""),
        "description":  (data.get("description","") or "")[:600],
        "full_text":    (data.get("full_text","")    or "")[:2000],
        "source_name":  data.get("source_name",""),
        "source_url":   data.get("source_url",""),
        "media_type":   data.get("media_type","news_scrape"),
        "location":     data.get("location","Rwanda"),
        "district":     data.get("district",""),
        "province":     data.get("province",""),
        "latitude":     data.get("latitude"),
        "longitude":    data.get("longitude"),
        "severity":     data.get("severity",1),
        "deaths":       deaths,
        "injured":      injured,
        "missing":      int(data.get("missing") or 0),
        "incident_type":data.get("incident_type","other"),
        "status":       data.get("status","active"),
        "detected_at":  datetime.utcnow().isoformat(),
        "published_at": data.get("published_at",""),
        "event_date":   data.get("event_date",""),
        "ai_summary":   data.get("ai_summary",""),
        "ai_confidence":float(data.get("ai_confidence") or 0.0),
        "is_historical":1 if data.get("is_historical") else 0,
        "verified":     0,
    })
    conn.commit()
    conn.close()
    return True


def log_scrape(source, scrape_type, started_at, finished_at, seen, added, error=None):
    conn = get_db()
    conn.execute("""
        INSERT INTO scrape_log (source,scrape_type,started_at,finished_at,
                                articles_seen,incidents_added,error)
        VALUES (?,?,?,?,?,?,?)
    """, (source, scrape_type, started_at, finished_at, seen, added, error))
    conn.commit()
    conn.close()


def get_cursor(source):
    conn = get_db()
    row = conn.execute("SELECT * FROM scrape_cursor WHERE source=?", (source,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_cursor(source, last_url="", last_date="", page=1):
    conn = get_db()
    conn.execute("""
        INSERT INTO scrape_cursor (source,last_url,last_date,page)
        VALUES (?,?,?,?)
        ON CONFLICT(source) DO UPDATE SET last_url=excluded.last_url,
            last_date=excluded.last_date, page=excluded.page
    """, (source, last_url, last_date, page))
    conn.commit()
    conn.close()
