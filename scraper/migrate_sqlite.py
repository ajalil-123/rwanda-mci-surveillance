"""
migrate_sqlite.py — one-time copy of the old SQLite database into Postgres.

    python jobs.py migrate-sqlite ../data/mci_rwanda.db

- Idempotent: rows whose source_id already exists are skipped.
- Drops records from blocked sources (replaces the old cleanup_blocked.py).
- Preserves incident IDs, then advances the identity sequence past them.
"""
import logging
import sqlite3
from pathlib import Path

from psycopg import sql

from database import get_db, init_db, source_id
from source_registry import is_blocked_source

logger = logging.getLogger("migrate")

INCIDENT_COLUMNS = [
    "id", "source_id", "semantic_id", "title", "description", "full_text",
    "source_name", "source_url", "source_tier", "media_type", "location",
    "district", "province", "latitude", "longitude", "severity", "deaths",
    "injured", "missing", "incident_type", "status", "detected_at",
    "published_at", "event_date", "ai_summary", "ai_confidence",
    "is_historical", "verified", "rwanda_verified",
]
# NOT NULL columns in Postgres that old SQLite rows may hold as NULL
DEFAULTS = {
    "source_tier": 3, "severity": 1, "deaths": 0, "injured": 0,
    "missing": 0, "is_historical": 0, "verified": 0,
}
BATCH = 500


def _sqlite_rows(path: Path, table: str) -> tuple[list[str], list[dict]]:
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in src.execute(f"SELECT * FROM {table}")]
        cols = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
    finally:
        src.close()
    return cols, rows


def migrate(path: Path) -> None:
    if not path.is_file():
        raise EnvironmentError(f"SQLite database not found: {path}")

    init_db()
    src_cols, rows = _sqlite_rows(path, "incidents")
    cols = [c for c in INCIDENT_COLUMNS if c in src_cols or c == "source_id"]

    kept, blocked = [], 0
    for r in rows:
        if is_blocked_source(source_name=r.get("source_name") or "", title=r.get("title") or "",
                             url=r.get("source_url") or ""):
            blocked += 1
            continue
        for k, v in DEFAULTS.items():
            if r.get(k) is None:
                r[k] = v
        r["source_id"] = r.get("source_id") or source_id(r.get("source_url") or "", r.get("title") or "")
        kept.append(tuple(r.get(c) for c in cols))

    insert = sql.SQL("INSERT INTO incidents ({}) VALUES ({}) ON CONFLICT (source_id) DO NOTHING").format(
        sql.SQL(", ").join(map(sql.Identifier, cols)),
        sql.SQL(", ").join(sql.Placeholder() * len(cols)),
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(kept), BATCH):
                cur.executemany(insert, kept[i:i + BATCH])
            # Identity must continue after the preserved IDs
            cur.execute("SELECT setval(pg_get_serial_sequence('incidents', 'id'), "
                        "COALESCE((SELECT MAX(id) FROM incidents), 0) + 1, false)")

            # scrape_cursor lets incremental scrapes resume where the old app stopped
            try:
                _, cursors = _sqlite_rows(path, "scrape_cursor")
            except sqlite3.OperationalError:  # very old databases had no cursor table
                cursors = []
            cur.executemany(
                "INSERT INTO scrape_cursor (source, last_url, last_date, page) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (source) DO NOTHING",
                [(c["source"], c.get("last_url"), c.get("last_date"), c.get("page") or 1) for c in cursors],
            )
            total = cur.execute("SELECT COUNT(*) AS n FROM incidents").fetchone()["n"]

    logger.info("Migrated %d incidents (%d blocked-source rows dropped). Postgres now holds %d.",
                len(kept), blocked, total)
