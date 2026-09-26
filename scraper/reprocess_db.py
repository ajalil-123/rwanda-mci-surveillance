"""
reprocess_db.py — Re-run fixed NLP on every existing database record.

What it does:
  1. Loads every incident from the database
  2. Re-runs is_rwanda_relevant() — deletes foreign conflict false positives
  3. Re-runs extract_deaths(), extract_injured(), extract_missing()
  4. Re-runs classify_incident_type() and calculate_severity()
  5. Re-runs geo_tag() to fix any mis-tagged districts
  6. Updates every record in-place (preserves IDs and dates)
  7. Prints a full summary of changes made

Run from the scraper/ folder (reads DATABASE_URL from the repo-root .env):
    python jobs.py reprocess
"""

import os, sys
from datetime import datetime

# ── make sure we can import from the same folder ──────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import get_db, init_db
from nlp import (
    enrich, is_rwanda_relevant, is_mci_relevant, is_civilian_mci,
    extract_deaths, extract_injured, extract_missing,
    classify_incident_type, calculate_severity, geo_tag,
)


# ── counters ──────────────────────────────────────────────────────────────────
stats = {
    "total":             0,
    "deleted":           0,
    "deleted_blocked":   0,
    "deleted_foreign":   0,
    "deleted_unknown":   0,
    "deleted_violence":  0,
    "deleted_zero_cas":  0,
    "deaths_updated":    0,
    "injured_updated":   0,
    "type_updated":      0,
    "sev_updated":       0,
    "geo_updated":       0,
    "unchanged":         0,
}

deleted_titles  = []
changed_records = []

def reprocess():
    conn = get_db()

    # fetch all records
    rows = conn.execute("""
        SELECT id, title, description, full_text,
               deaths, injured, missing,
               incident_type, severity,
               district, province, latitude, longitude,
               source_name, source_url, media_type
        FROM incidents
        ORDER BY id
    """).fetchall()

    stats["total"] = len(rows)
    print(f"\n{'='*60}")
    print("  NHIC MCI Database Reprocessor")
    print(f"  Records to process: {len(rows)}")
    print(f"{'='*60}\n")

    for row in rows:
        row   = dict(row)
        iid   = row["id"]
        title = row["title"] or ""

        # combine all text for NLP
        text = " ".join(filter(None, [
            row.get("title",""),
            row.get("description",""),
            row.get("full_text",""),
        ]))

        # ── Step 0: Blocked sources (BBC, VOA, etc.) — delete entirely ────
        try:
            from source_registry import is_blocked_source
            if is_blocked_source(
                source_name=row.get("source_name",""),
                title=title,
                url=row.get("source_url",""),
            ):
                conn.execute("DELETE FROM incidents WHERE id=%s", (iid,))
                stats["deleted"] += 1
                stats["deleted_blocked"] = stats.get("deleted_blocked",0) + 1
                deleted_titles.append(f"  [{iid}] [blocked source] {title[:65]}")
                continue
        except Exception:
            pass

        # ── Step 1: Rwanda relevance check — delete if false positive ─────
        if not is_rwanda_relevant(text):
            conn.execute("DELETE FROM incidents WHERE id=%s", (iid,))
            stats["deleted"] += 1
            stats["deleted_foreign"] += 1
            deleted_titles.append(f"  [{iid}] [foreign] {title[:75]}")
            continue

        # ── Step 1c: Civilian MCI check — delete war/violence/off-topic ──
        if not is_civilian_mci(text):
            conn.execute("DELETE FROM incidents WHERE id=%s", (iid,))
            stats["deleted"] += 1
            stats["deleted_violence"] += 1
            deleted_titles.append(f"  [{iid}] [war/violence/off-topic] {title[:65]}")
            continue

        # ── Step 1d: Require at least 1 casualty (death or injured) ──────
        # Re-extract with fixed NLP first, then check
        pre_deaths  = extract_deaths(text)
        pre_injured = extract_injured(text)
        if pre_deaths == 0 and pre_injured == 0:
            conn.execute("DELETE FROM incidents WHERE id=%s", (iid,))
            stats["deleted"] += 1
            stats["deleted_zero_cas"] += 1
            deleted_titles.append(f"  [{iid}] [zero casualties] {title[:70]}")
            continue

        # ── Step 1b: Try geo_tag first to see if we can resolve the location ─
        geo_check = geo_tag(text)
        still_unknown = (
            geo_check["district"] in ("", "Unknown") and
            geo_check["province"] in ("", "Unknown")
        )
        stored_district = (row.get("district") or "").strip()
        stored_province = (row.get("province") or "").strip()
        stored_unknown  = stored_district in ("", "Unknown") and \
                          stored_province in ("", "Unknown")

        if still_unknown and stored_unknown:
            # Last chance: re-extract deaths — if we can get a death count
            # from the text, the record has value even without a district.
            # Only delete if we truly cannot extract any useful information.
            re_deaths  = extract_deaths(text)
            re_injured = extract_injured(text)
            if re_deaths == 0 and re_injured == 0:
                # No casualties extractable and no location — not useful
                conn.execute("DELETE FROM incidents WHERE id=%s", (iid,))
                stats["deleted"] += 1
                stats["deleted_unknown"] += 1
                deleted_titles.append(f"  [{iid}] [unknown location] {title[:70]}")
                continue
            # Has casualties but no district — keep it, mark province as "Rwanda"
            conn.execute("""
                UPDATE incidents SET province='Rwanda (unspecified)', district='Unknown'
                WHERE id=%s
            """, (iid,))
            # fall through to normal NLP update below

        changes = {}

        # ── Step 2: Re-extract deaths ─────────────────────────────────────
        new_deaths = extract_deaths(text)
        if new_deaths != (row["deaths"] or 0):
            changes["deaths"] = (row["deaths"] or 0, new_deaths)
            stats["deaths_updated"] += 1

        # ── Step 3: Re-extract injured ────────────────────────────────────
        new_injured = extract_injured(text)
        if new_injured != (row["injured"] or 0):
            changes["injured"] = (row["injured"] or 0, new_injured)
            stats["injured_updated"] += 1

        # ── Step 4: Re-extract missing ────────────────────────────────────
        new_missing = extract_missing(text)

        # ── Step 5: Re-classify incident type ────────────────────────────
        new_type = classify_incident_type(text)
        if new_type != (row["incident_type"] or "other"):
            changes["incident_type"] = (row["incident_type"], new_type)
            stats["type_updated"] += 1

        # ── Step 6: Re-calculate severity ────────────────────────────────
        # Use updated death count for severity
        import re as _re
        # temporarily patch deaths in text for severity calc
        new_sev = calculate_severity(text)
        # also boost by new death count
        if new_deaths >= 50:   new_sev = max(new_sev, 5)
        elif new_deaths >= 20: new_sev = max(new_sev, 4)
        elif new_deaths >= 5:  new_sev = max(new_sev, 3)
        elif new_deaths >= 1:  new_sev = max(new_sev, 2)
        new_sev = max(1, new_sev)

        if new_sev != (row["severity"] or 1):
            changes["severity"] = (row["severity"], new_sev)
            stats["sev_updated"] += 1

        # ── Step 7: Re-run geo tagging ────────────────────────────────────
        geo = geo_tag(text)
        geo_changed = (
            geo["district"] != (row["district"] or "") or
            geo["province"] != (row["province"] or "")
        )
        if geo_changed and geo["district"] not in ("", "Unknown"):
            changes["geo"] = (
                f"{row['district']}/{row['province']}",
                f"{geo['district']}/{geo['province']}"
            )
            stats["geo_updated"] += 1

        # ── Apply updates ─────────────────────────────────────────────────
        if changes:
            conn.execute("""
                UPDATE incidents SET
                    deaths        = %s,
                    injured       = %s,
                    missing       = %s,
                    incident_type = %s,
                    severity      = %s,
                    district      = CASE WHEN %s != 'Unknown' THEN %s ELSE district END,
                    province      = CASE WHEN %s != 'Unknown' THEN %s ELSE province END,
                    latitude      = CASE WHEN %s != 'Unknown' THEN %s ELSE latitude END,
                    longitude     = CASE WHEN %s != 'Unknown' THEN %s ELSE longitude END
                WHERE id = %s
            """, (
                new_deaths, new_injured, new_missing,
                new_type, new_sev,
                geo["district"], geo["district"],
                geo["district"], geo["province"],
                geo["district"], geo["latitude"],
                geo["district"], geo["longitude"],
                iid,
            ))
            changed_records.append({
                "id":     iid,
                "title":  title[:70],
                "changes": changes,
            })
        else:
            stats["unchanged"] += 1

    conn.commit()
    conn.close()

    # ── Print report ──────────────────────────────────────────────────────
    print(f"{'─'*60}")
    print(f"  DELETED: {stats['deleted']} total")
    print(f"    Blocked sources (BBC, VOA, etc): {stats['deleted_blocked']}")
    print(f"    Foreign conflict / not Rwanda  : {stats['deleted_foreign']}")
    print(f"    War / violence / off-topic     : {stats['deleted_violence']}")
    print(f"    Zero casualties                : {stats['deleted_zero_cas']}")
    print(f"    Unknown location (no district) : {stats['deleted_unknown']}")
    if deleted_titles:
        for t in deleted_titles[:30]:
            print(f"    ✗ {t}")
        if len(deleted_titles) > 30:
            print(f"    … and {len(deleted_titles)-30} more")

    print(f"\n{'─'*60}")
    print(f"  UPDATED RECORDS: {len(changed_records)}")

    # show records where deaths changed
    death_changes = [r for r in changed_records if "deaths" in r["changes"]]
    if death_changes:
        print(f"\n  Death count corrections ({len(death_changes)}):")
        for r in death_changes[:30]:
            old, new = r["changes"]["deaths"]
            print(f"    [{r['id']}] {old} → {new}  | {r['title']}")

    # show type changes
    type_changes = [r for r in changed_records if "incident_type" in r["changes"]]
    if type_changes:
        print(f"\n  Type corrections ({len(type_changes)}):")
        for r in type_changes[:20]:
            old, new = r["changes"]["incident_type"]
            print(f"    [{r['id']}] {old} → {new}  | {r['title']}")

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Total records processed   : {stats['total']}")
    print(f"  Deleted total             : {stats['deleted']}")
    print(f"    → Blocked sources       : {stats['deleted_blocked']}")
    print(f"    → Foreign / off-topic   : {stats['deleted_foreign']}")
    print(f"    → War / violence        : {stats['deleted_violence']}")
    print(f"    → Zero casualties       : {stats['deleted_zero_cas']}")
    print(f"    → Unknown location      : {stats['deleted_unknown']}")
    print(f"  Deaths updated           : {stats['deaths_updated']}")
    print(f"  Injured updated          : {stats['injured_updated']}")
    print(f"  Incident type updated    : {stats['type_updated']}")
    print(f"  Severity updated         : {stats['sev_updated']}")
    print(f"  Geo updated              : {stats['geo_updated']}")
    print(f"  Unchanged                : {stats['unchanged']}")
    print(f"{'='*60}")
    print("\n  Done. The dashboard reflects the changes on its next refresh.\n")


def deduplicate_existing():
    """
    Merge existing duplicate records that cover the same event.

    Strategy:
      1. Compute semantic_id for every record using the fixed NLP
      2. Group records by semantic_id
      3. For each group with >1 record: keep the BEST one, delete the rest
         Best = highest deaths count, then most complete data, then earliest detected

    A record qualifies for semantic grouping only if it has deaths>0 or injured>0.
    Zero-casualty records are never merged (they may be genuinely different events).
    """
    from database import make_semantic_id, get_db

    print(f"\n{'='*60}")
    print(f"  SEMANTIC DEDUPLICATION")
    print(f"{'='*60}")

    conn = get_db()
    rows = conn.execute("""
        SELECT id, title, event_date, published_at, deaths, injured,
               incident_type, district, province, source_name, detected_at,
               description, ai_summary
        FROM incidents
        WHERE (deaths > 0 OR injured > 0)
        ORDER BY deaths DESC, detected_at ASC
    """).fetchall()

    # Group by semantic_id
    groups = {}
    for row in rows:
        row = dict(row)
        sem = make_semantic_id(row)
        if sem not in groups:
            groups[sem] = []
        groups[sem].append(row)

    total_removed = 0
    groups_merged = 0
    merge_log = []

    for sem_id, group in groups.items():
        if len(group) <= 1:
            continue

        # Sort: prefer records with known district, higher deaths, earlier date
        def score(r):
            has_district = 1 if r.get("district","") not in ("","Unknown") else 0
            has_summary  = 1 if r.get("ai_summary","") else 0
            return (has_district * 10 + r.get("deaths",0) * 2 + has_summary, r["id"])

        group.sort(key=score, reverse=True)
        keep    = group[0]
        discard = group[1:]

        # Update semantic_id on the keeper so future scrapes know it's taken
        conn.execute("UPDATE incidents SET semantic_id=%s WHERE id=%s",
                     (sem_id, keep["id"]))

        # Delete duplicates
        discard_ids = [r["id"] for r in discard]
        conn.execute(
            "DELETE FROM incidents WHERE id = ANY(%s)", (discard_ids,)
        )
        total_removed += len(discard_ids)
        groups_merged += 1

        merge_log.append({
            "kept":     keep,
            "removed":  discard,
        })

    conn.commit()
    conn.close()

    # Report
    if merge_log:
        print(f"  Found {groups_merged} duplicate event groups, removed {total_removed} records\n")
        for m in merge_log[:20]:
            k = m["kept"]
            print(f"  KEPT  [{k['id']}] {k['title'][:65]}")
            for r in m["removed"]:
                print(f"    ✗   [{r['id']}] {r['title'][:65]}")
            print()
        if len(merge_log) > 20:
            print(f"  … and {len(merge_log)-20} more groups")
    else:
        print(f"  No duplicate events found.")

    print(f"  Total duplicate records removed: {total_removed}")
    print(f"{'='*60}\n")
    return total_removed


def backfill_source_tiers():
    """
    Backfill source_tier column on existing records.
    Also overwrites source_name with the real publisher when the original
    source was an aggregator (Google News, AllAfrica).
    """
    from source_registry import classify_from_title_and_source, TIER_INFO

    print(f"\n{'='*60}")
    print(f"  SOURCE TIER CLASSIFICATION")
    print(f"{'='*60}")

    conn = get_db()
    rows = conn.execute("""
        SELECT id, title, source_name, source_tier
        FROM incidents
    """).fetchall()
    counts   = {1:0, 2:0, 3:0}
    updated  = 0
    renamed  = 0
    for row in rows:
        old_source = row["source_name"] or ""
        new_tier, new_source = classify_from_title_and_source(
            row["title"] or "", old_source
        )
        counts[new_tier] += 1

        changes = []
        if row["source_tier"] != new_tier:
            changes.append(("source_tier", new_tier))
        if new_source and new_source != old_source:
            changes.append(("source_name", new_source))
            renamed += 1

        if changes:
            set_clauses = ", ".join(f"{c}=%s" for c,_ in changes)
            vals = [v for _,v in changes] + [row["id"]]
            conn.execute(f"UPDATE incidents SET {set_clauses} WHERE id=%s", vals)
            updated += 1

    conn.commit()
    conn.close()

    print(f"  Updated tier on {updated} records")
    print(f"  Renamed source on {renamed} records (extracted real publisher from title)")
    print(f"  Distribution:")
    for t in [1, 2, 3]:
        info = TIER_INFO[t]
        print(f"    Tier {t} ({info['label'][:35]:<35}): {counts[t]} records")
    print(f"{'='*60}\n")
    return updated


def run_all(assume_yes: bool = False) -> None:
    """Reprocess, deduplicate and backfill tiers across the whole database."""
    if not assume_yes:
        answer = input("\nThis will update and deduplicate every record in the database. Continue? (yes/no): ")
        if answer.strip().lower() not in ("yes", "y"):
            print("Cancelled.")
            return
    init_db()
    reprocess()
    deduplicate_existing()
    backfill_source_tiers()


if __name__ == "__main__":
    run_all(assume_yes="--yes" in sys.argv)
