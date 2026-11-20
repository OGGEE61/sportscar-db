"""Find stored otomoto ads whose VIN is behind "Wyświetl VIN" but that were saved as having none.

The scraper tells a VIN behind the button by a flag in the ad page (VIN_FLAG_KEYS in
base_scraper). When otomoto renames that flag, new ads are saved with vin_confidence 'none' and
their VIN is never revealed, and the scraper doesn't open known ads again. After adding the new
flag, run this: it opens every pending otomoto ad saved without a VIN and flags the ones whose
page now says the VIN is there, so scripts/maintenance/reveal_pending_vins.py reveals them.
It sets only the flag; the VIN itself comes from the reveal. Ads Otomoto already answered
without a VIN ('not_shown', the seller masked it) are not opened: a reveal would only use the
day's limit again.

Usage: python scripts/maintenance/recheck_hidden_vins.py [--yes]

  (no flag)  list what would be flagged, change nothing
  --yes      flag them

Writes against the backend selected by DB_BACKEND (d1 = production).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
from base_scraper import fetch_detail
from db import get_db

DELAY_S = 1.0


def main():
    conn = get_db()
    ads = conn.execute("""
        SELECT id, source_listing_id, source_url, variant FROM pending_listings
        WHERE source = 'otomoto' AND status = 'pending' AND COALESCE(TRIM(vin), '') = ''
          AND vin_confidence = 'none' AND source_url IS NOT NULL
        ORDER BY id DESC
    """).fetchall()
    print(f"Opening {len(ads)} pending otomoto ads saved without a VIN...")
    found = []
    for i, ad in enumerate(ads):
        if i:
            time.sleep(DELAY_S)
        detail = fetch_detail(ad["source_url"]) or {}
        if detail.get("vin_confidence") != "found_in_schema":
            continue
        found.append(ad)
        print(f"  [vin behind the button] {ad['source_listing_id']} {ad['variant']}")
        if "--yes" in sys.argv:
            conn.execute("UPDATE pending_listings SET vin_confidence = 'found_in_schema' "
                         "WHERE id = ? AND vin_confidence = 'none'", (ad["id"],))
            conn.commit()
    conn.close()
    print(f"\n{len(found)} of {len(ads)} have a VIN to reveal.")
    print("Flagged: the VIN reveal job takes them next." if "--yes" in sys.argv
          else "Nothing changed. Run with --yes to flag them.")


if __name__ == "__main__":
    main()
