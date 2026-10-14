"""Clear wrong "sold" stamps made before the sold-marking fix (PR #4).

A listing is wrongly stamped when one of its observations has removed_at set
but another observation of the same listing was recorded after that moment.
Changed rows are copied to a JSON backup before anything is updated.

Usage: python scripts/maintenance/fix_false_sold.py [--dry-run] [--yes]

Writes against the backend selected by DB_BACKEND (d1 = production) and asks
for confirmation first; --yes skips the prompt.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import db
from db import get_db

QUERY = """
    SELECT o.* FROM listing_observations o
    WHERE o.removed_at IS NOT NULL
      AND o.source_listing_id IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM listing_observations n
        WHERE n.source = o.source AND n.source_listing_id = o.source_listing_id
          AND n.id <> o.id AND n.observed_at > o.removed_at)
"""


def main():
    dry_run = "--dry-run" in sys.argv
    conn = get_db()
    rows = [dict(r) for r in conn.execute(QUERY).fetchall()]
    print(f"{len(rows)} observation(s) wrongly marked as removed (backend: {os.environ.get('DB_BACKEND', 'sqlite')})")
    for r in rows:
        print(f"  #{r['id']} {r['source']}:{r['source_listing_id']} removed_at={r['removed_at']}")
    if dry_run or not rows:
        conn.close()
        return

    backend = os.environ.get("DB_BACKEND", "sqlite").lower()
    target = "PRODUCTION (Cloudflare D1)" if backend == "d1" else f"local SQLite ({db.DB_PATH})"
    if "--yes" not in sys.argv:
        if not sys.stdin.isatty():
            sys.exit(f"Refusing to write to {target} non-interactively; pass --yes to confirm.")
        if input(f"Clear removed_at on {len(rows)} row(s) in {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted, nothing changed.")

    backup = f"false_sold_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(backup, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"Backup written to {backup}")

    for r in rows:
        conn.execute("UPDATE listing_observations SET removed_at = NULL WHERE id = ?", (r["id"],))
    conn.commit()
    conn.close()
    print(f"Cleared removed_at on {len(rows)} row(s)")


if __name__ == "__main__":
    main()
