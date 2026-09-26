"""
jobs.py — command-line entry point for every scheduled / admin task.

Replaces the Flask background threads. GitHub Actions runs `scrape` + `verify`
on a schedule; everything else is run by hand when needed.

    python jobs.py init-db
    python jobs.py scrape [--historical]
    python jobs.py verify      [--limit 100] [--all]
    python jobs.py summarize   [--limit 50]  [--mci-only]
    python jobs.py reclassify  [--limit 100]
    python jobs.py reprocess   [--yes]
    python jobs.py migrate-sqlite path/to/mci_rwanda.db

Reads DATABASE_URL (and optionally ANTHROPIC_API_KEY) from the environment,
or from the repo-root .env when running locally.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# One .env at the repo root, shared with the frontend
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("jobs")

MCI_THRESHOLD = 3  # keep in sync with frontend/src/server/queries.ts

VALID_TYPES = {
    "road_accident", "flood", "landslide", "explosion", "fire",
    "stampede", "outbreak", "drowning", "building_collapse", "violence",
}

AI_COLUMNS = ("id, title, description, full_text, source_name, source_url, district, province, "
              "incident_type, deaths, injured, event_date, published_at")


def _require_anthropic() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise EnvironmentError("ANTHROPIC_API_KEY is not set — AI jobs need it.")


def _fetch(sql: str, params=()) -> list[dict]:
    from database import get_db
    with get_db() as conn:
        return conn.execute(sql, params).fetchall()


def _update(sql: str, params) -> None:
    from database import get_db
    with get_db() as conn:  # commits on clean exit
        conn.execute(sql, params)


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_init_db(_args) -> None:
    from database import init_db
    init_db()
    logger.info("Schema is up to date.")


def cmd_scrape(args) -> None:
    from database import init_db
    from scraper import run_historical_scrape, run_incremental_scrape
    init_db()
    results = run_historical_scrape() if args.historical else run_incremental_scrape()
    logger.info("Scrape finished: %s new incidents %s", sum(results.values()), results)


def cmd_verify(args) -> None:
    """Confirm Rwanda relevance with Claude. Rejected rows drop out of the dashboard view."""
    from claude_ai import verify_rwanda_relevance
    _require_anthropic()
    where = "TRUE" if args.all else "rwanda_verified IS NULL"
    rows = _fetch(f"SELECT {AI_COLUMNS} FROM incidents WHERE {where} ORDER BY deaths DESC LIMIT %s", (args.limit,))
    kept = rejected = 0
    for inc in rows:
        result = verify_rwanda_relevance(inc)
        if result["is_rwanda"] is None:  # Claude unavailable — leave unverified, retry next run
            continue
        verified = 1 if result["is_rwanda"] else 0
        _update("UPDATE incidents SET rwanda_verified = %s WHERE id = %s", (verified, inc["id"]))
        if verified:
            kept += 1
        else:
            rejected += 1
            logger.info("Rejected #%s (%s): %s — %s", inc["id"], result.get("rejection_category"),
                        inc["title"][:60], result.get("reason", ""))
    logger.info("Verify complete: %d checked, %d kept, %d rejected", len(rows), kept, rejected)


def cmd_summarize(args) -> None:
    """Generate AI summaries for incidents that don't have one."""
    from claude_ai import summarize_incident
    _require_anthropic()
    where = "(ai_summary IS NULL OR ai_summary = '')"
    if args.mci_only:
        where += f" AND deaths >= {MCI_THRESHOLD}"
    rows = _fetch(f"SELECT * FROM incidents WHERE {where} ORDER BY deaths DESC LIMIT %s", (args.limit,))
    done = 0
    for inc in rows:
        try:
            result = summarize_incident(inc)
        except Exception as exc:
            logger.warning("summarize #%s failed: %s", inc["id"], exc)
            continue
        if result.get("summary"):
            _update(
                "UPDATE incidents SET ai_summary = %s, ai_confidence = %s WHERE id = %s",
                (result["summary"], result.get("confidence", 0.0), inc["id"]),
            )
            done += 1
    logger.info("Summarize complete: %d of %d updated", done, len(rows))


def cmd_reclassify(args) -> None:
    """Re-type incidents stuck as 'other'; delete those Claude still can't classify."""
    from claude_ai import verify_rwanda_relevance
    _require_anthropic()
    rows = _fetch(
        f"SELECT {AI_COLUMNS} FROM incidents "
        "WHERE incident_type IS NULL OR incident_type IN ('', 'other') "
        "ORDER BY deaths DESC LIMIT %s",
        (args.limit,),
    )
    updated = deleted = 0
    for inc in rows:
        result = verify_rwanda_relevance(inc)
        if result["is_rwanda"] is None:  # Claude unavailable — never delete on an error
            continue
        new_type = result["incident_type"]
        if new_type in VALID_TYPES:
            _update("UPDATE incidents SET incident_type = %s WHERE id = %s", (new_type, inc["id"]))
            updated += 1
        else:
            _update("DELETE FROM incidents WHERE id = %s", (inc["id"],))
            deleted += 1
    logger.info("Reclassify complete: %d updated, %d deleted", updated, deleted)


def cmd_reprocess(args) -> None:
    from reprocess_db import run_all
    run_all(assume_yes=args.yes)


def cmd_migrate_sqlite(args) -> None:
    from migrate_sqlite import migrate
    migrate(Path(args.path))


def main() -> int:
    parser = argparse.ArgumentParser(description="NHIC MCI surveillance jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create/upgrade the schema").set_defaults(func=cmd_init_db)

    p = sub.add_parser("scrape", help="scrape sources (incremental by default)")
    p.add_argument("--historical", action="store_true", help="full backfill from 2010 (slow)")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("verify", help="Claude Rwanda-relevance check")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--all", action="store_true", help="re-check already verified rows too")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("summarize", help="Claude incident summaries")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--mci-only", action="store_true")
    p.set_defaults(func=cmd_summarize)

    p = sub.add_parser("reclassify", help="Claude re-typing of 'other' incidents")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_reclassify)

    p = sub.add_parser("reprocess", help="re-run NLP + dedup + tier backfill on all rows")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(func=cmd_reprocess)

    p = sub.add_parser("migrate-sqlite", help="one-time copy of a local SQLite DB into Postgres")
    p.add_argument("path", help="path to mci_rwanda.db")
    p.set_defaults(func=cmd_migrate_sqlite)

    args = parser.parse_args()
    try:
        args.func(args)
    except (EnvironmentError, ImportError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
