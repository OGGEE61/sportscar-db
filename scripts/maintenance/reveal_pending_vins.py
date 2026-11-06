"""Reveal missing VINs of Otomoto listings waiting in the review queue, from this machine.

Otomoto blocks VIN reveals from GitHub's runners after a burst (HTTP 403), but answers a normal
connection. This fills in pending Otomoto listings whose ad has a VIN that the scraper could not
reveal, at the scraper's pace (base_scraper.VIN_REVEAL_DELAY_S), and stops at the first 403.
A VIN is stored only if it passes validation.is_plausible_vin, the same check the scraper uses.
Only pending_listings.vin is filled in: nothing is approved, rejected or deleted.

Needs a logged-in scrapers/otomoto_cookies.json.

Usage: python scripts/maintenance/reveal_pending_vins.py [--limit N]

Writes against the backend selected by DB_BACKEND (d1 = production).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
import base_scraper
from base_scraper import check_session, load_cookies, refresh_session, reveal_vin
from db import get_db
from validation import is_plausible_vin


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    cookies = refresh_session(load_cookies(), log_errors=False)
    if not check_session(cookies):
        sys.exit("Not logged in to Otomoto: update scrapers/otomoto_cookies.json first.")
    # The per-run cap is for the scheduled runs; here the pace and the stop on 403 are enough
    base_scraper.VIN_REVEALS_PER_RUN = 10 ** 6

    conn = get_db()
    rows = conn.execute("""
        SELECT id, source_listing_id, variant FROM pending_listings
        WHERE source = 'otomoto' AND status = 'pending' AND (vin IS NULL OR vin = '')
          AND vin_confidence = 'found_in_schema'
        ORDER BY id DESC
    """).fetchall()
    rows = rows[:limit] if limit else rows
    print(f"{len(rows)} pending Otomoto listings with a VIN behind 'Show VIN'.")

    found = 0
    for i, r in enumerate(rows, 1):
        if not base_scraper.vin_reveal_allowed():
            print("Stopped: Otomoto blocked the reveals (HTTP 403).")
            break
        vin = reveal_vin(r["source_listing_id"], cookies)
        if vin and is_plausible_vin(vin):
            conn.execute("UPDATE pending_listings SET vin = ? WHERE id = ? AND (vin IS NULL OR vin = '')",
                         (vin, r["id"]))
            conn.commit()
            found += 1
        print(f"  [{i}/{len(rows)}] {r['variant']} {r['source_listing_id']}: {'VIN' if vin else 'no VIN'}", flush=True)
    print(f"Done: {found} VINs filled in.")


if __name__ == "__main__":
    main()
