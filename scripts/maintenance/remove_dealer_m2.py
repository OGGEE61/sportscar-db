"""Remove dealer-stock BMW M2 listings: under a year old with under 20 000 km.

Same rule the M2 G87 scrapers now apply (validation.is_dealer_new_m2), applied to data
already stored, judged at the time each listing was seen. Removes:
  - matching listing_observations (per listing, so a car resold later keeps its other ads)
  - vehicles left without any observation
  - pending (unreviewed) listings
Everything removed is copied to a JSON backup first.

Usage: python scripts/maintenance/remove_dealer_m2.py [--dry-run] [--yes]

Writes against the backend selected by DB_BACKEND (d1 = production) and asks
for confirmation first; --yes skips the prompt.
"""
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import db
from db import get_db
from validation import is_dealer_new_m2


def seen_on(row):
    try:
        return date.fromisoformat((row["first_seen_at"] or row["observed_at"] or "")[:10])
    except ValueError:
        return None


def main():
    dry_run = "--dry-run" in sys.argv
    conn = get_db()

    obs = [dict(r) for r in conn.execute("""
        SELECT o.*, v.year AS v_year, v.first_registration_date AS v_first_reg, v.model AS v_model
        FROM listing_observations o JOIN vehicles v ON v.vin = o.vin
        WHERE v.make = 'BMW' AND v.model = 'M2' AND o.mileage_km < 20000""").fetchall()]
    obs = [o for o in obs if seen_on(o) and is_dealer_new_m2(
        o["v_model"], o["v_year"], o["mileage_km"], o["v_first_reg"], on=seen_on(o))]

    pending = [dict(r) for r in conn.execute("""
        SELECT * FROM pending_listings
        WHERE status = 'pending' AND make = 'BMW' AND model = 'M2' AND mileage_km < 20000""").fetchall()]
    pending = [p for p in pending if is_dealer_new_m2(
        p["model"], p["year"], p["mileage_km"], p["first_registration_date"])]

    gone = {o["id"] for o in obs}
    orphans = []
    for vin in sorted({o["vin"] for o in obs}):
        left = conn.execute("SELECT id FROM listing_observations WHERE vin = ?", (vin,)).fetchall()
        if all(r["id"] in gone for r in left):
            orphans.append(dict(conn.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,)).fetchone()))

    backend = os.environ.get("DB_BACKEND", "sqlite")
    print(f"{len(obs)} observation(s), {len(orphans)} vehicle(s) left empty, "
          f"{len(pending)} pending listing(s) (backend: {backend})")
    for o in obs:
        print(f"  obs #{o['id']} {o['source']}:{o['source_listing_id']} {o['vin']} "
              f"{o['v_year']} {o['mileage_km']} km seen {o['first_seen_at'] or o['observed_at']}")
    for p in pending:
        print(f"  pending #{p['id']} {p['source']}:{p['source_listing_id']} {p['year']} {p['mileage_km']} km")
    if dry_run or not (obs or pending):
        conn.close()
        return

    target = "PRODUCTION (Cloudflare D1)" if backend.lower() == "d1" else f"local SQLite ({db.DB_PATH})"
    if "--yes" not in sys.argv:
        if not sys.stdin.isatty():
            sys.exit(f"Refusing to write to {target} non-interactively; pass --yes to confirm.")
        if input(f"Delete these rows from {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted, nothing changed.")

    backup = f"dealer_m2_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(backup, "w") as f:
        json.dump({"observations": obs, "vehicles": orphans, "pending": pending}, f, indent=2, default=str)
    print(f"Backup written to {backup}")

    for o in obs:
        conn.execute("DELETE FROM listing_observations WHERE id = ?", (o["id"],))
    for v in orphans:
        conn.execute("DELETE FROM vehicles WHERE vin = ?", (v["vin"],))
    for p in pending:
        conn.execute("DELETE FROM pending_listings WHERE id = ?", (p["id"],))
    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
