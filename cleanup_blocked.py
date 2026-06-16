"""
cleanup_blocked.py — Remove BBC, Voice of America, and other blocked sources
from the existing database. Run once after updating source_registry.py.
"""
import sqlite3, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_registry import is_blocked_source

db_path = os.path.join("data", "mci_rwanda.db")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, source_name, title, source_url FROM incidents"
).fetchall()

deleted = 0
for r in rows:
    if is_blocked_source(r["source_name"], r["title"], r["source_url"]):
        conn.execute("DELETE FROM incidents WHERE id=?", (r["id"],))
        deleted += 1
        print(f"  x [{r['id']}] {r['title'][:65]}")

conn.commit()
conn.close()

print(f"\nDeleted {deleted} BBC/VOA/blocked records out of {len(rows)} total")
