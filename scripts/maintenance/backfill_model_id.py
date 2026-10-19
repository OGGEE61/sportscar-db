"""Fill vehicles.model_id from the model catalog rules (webapp/model_catalog.py).

Only vehicles without a model_id are touched. A vehicle is skipped (and listed)
when no rule or more than one rule matches, so nothing is guessed.

Usage: python scripts/maintenance/backfill_model_id.py [--dry-run] [--yes]
Writes to the backend selected by DB_BACKEND (d1 = production) after confirmation.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import db
from webapp.model_catalog import resolve_model_ids


def main():
    conn = db.get_db()
    have = {r[1] for r in conn.execute("PRAGMA table_info(vehicles)").fetchall()}
    if "model_id" not in have:
        sys.exit("vehicles.model_id is missing - run `python db.py` first to migrate.")
    todo = {r["vin"] for r in conn.execute("SELECT vin FROM vehicles WHERE model_id IS NULL").fetchall()}
    resolved = {vin: mid for vin, mid in resolve_model_ids(conn).items() if vin in todo}
    assign = {vin: mid for vin, mid in resolved.items() if mid}
    skipped = [vin for vin, mid in resolved.items() if not mid]

    print(f"{len(todo)} vehicle(s) without model_id: {len(assign)} resolvable, {len(skipped)} unmatched/ambiguous")
    for mid, n in Counter(assign.values()).most_common():
        print(f"  {n:5d}  {mid}")
    if "--dry-run" in sys.argv or not assign:
        conn.close()
        return

    backend = os.environ.get("DB_BACKEND", "sqlite").lower()
    target = "PRODUCTION (Cloudflare D1)" if backend == "d1" else f"local SQLite ({db.DB_PATH})"
    if "--yes" not in sys.argv:
        if not sys.stdin.isatty():
            sys.exit(f"Refusing to write to {target} non-interactively; pass --yes to confirm.")
        if input(f"Set model_id on {len(assign)} vehicle(s) in {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted, nothing changed.")

    for vin, mid in assign.items():
        conn.execute("UPDATE vehicles SET model_id = ? WHERE vin = ? AND model_id IS NULL", (mid, vin))
    conn.commit()
    conn.close()
    print(f"Set model_id on {len(assign)} vehicle(s)")


if __name__ == "__main__":
    main()
