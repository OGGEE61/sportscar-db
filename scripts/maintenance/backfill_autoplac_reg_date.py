"""Fill first_registration_date for autoplac listings stored before the parser read it.

Known autoplac listings with VIN + plate skip the detail page, so scraper runs never fill this.
Only empty dates are written, and only when the live page still shows the VIN we have stored.

Usage: python scripts/maintenance/backfill_autoplac_reg_date.py [--dry-run] [--yes]
Writes to the backend selected by DB_BACKEND (d1 = production) after confirmation.
"""
import os
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scrapers"))
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
import db
import base_scraper
from validation import is_valid_first_registration_date


def main():
    dry_run = "--dry-run" in sys.argv
    conn = db.get_db()
    rows = conn.execute("""
        SELECT id, vin, source_url FROM pending_listings
        WHERE source = 'autoplac' AND status = 'approved'
          AND vin IS NOT NULL AND vin != ''
          AND (first_registration_date IS NULL OR first_registration_date = '')
          AND source_url IS NOT NULL AND source_url != ''
        ORDER BY id
    """).fetchall()
    print(f"{len(rows)} autoplac listing(s) without a first registration date")

    found = {}
    outcome = Counter()
    for r in rows:
        detail = base_scraper.fetch_detail(r["source_url"]) or {}
        date = detail.get("first_registration_date")
        if detail.get("vin") != r["vin"]:
            outcome["page gone or shows another VIN"] += 1
        elif not is_valid_first_registration_date(date):
            outcome["no valid date on the page"] += 1
        else:
            outcome["date found"] += 1
            found[r["id"]] = (r["vin"], date)
        time.sleep(1.0)
    for name, n in outcome.most_common():
        print(f"  {n:5d}  {name}")
    if dry_run or not found:
        conn.close()
        return

    backend = os.environ.get("DB_BACKEND", "sqlite").lower()
    target = "PRODUCTION (Cloudflare D1)" if backend == "d1" else f"local SQLite ({db.DB_PATH})"
    if "--yes" not in sys.argv:
        if not sys.stdin.isatty():
            sys.exit(f"Refusing to write to {target} non-interactively; pass --yes to confirm.")
        if input(f"Fill dates on {len(found)} listing(s) in {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted, nothing changed.")

    for listing_id, (vin, date) in found.items():
        conn.execute("""UPDATE pending_listings SET first_registration_date = ?
                        WHERE id = ? AND (first_registration_date IS NULL OR first_registration_date = '')""",
                     (date, listing_id))
        conn.execute("""UPDATE vehicles SET first_registration_date = ?, updated_at = datetime('now')
                        WHERE vin = ? AND (first_registration_date IS NULL OR first_registration_date = '')""",
                     (date, vin))
    conn.commit()
    conn.close()
    print(f"Filled dates on {len(found)} listing(s)")


if __name__ == "__main__":
    main()
