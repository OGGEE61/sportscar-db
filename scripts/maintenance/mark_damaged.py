"""Record stored ads that their site marks as damaged.

New ads are recorded when scraped; this applies the same check to ads already stored, by opening
every ad that is still online. Nothing is hidden or deleted: the ad goes into damaged_listings, so
the car's VIN shows it was sold as damaged and its price is left out of the price charts and
averages. Ads no longer online can't be checked and are left as they are.

Usage: python scripts/maintenance/mark_damaged.py [--yes] [--undo]

  (no flag)  list what would be recorded, change nothing
  --yes      record them
  --undo     forget every recorded ad

Writes against the backend selected by DB_BACKEND (d1 = production).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
from db import get_db
from base_scraper import _safe, fetch_detail

DELAY_S = 1.0


def main():
    conn = get_db()
    if "--undo" in sys.argv:
        conn.execute("DELETE FROM damaged_listings")
        conn.commit()
        print("Recorded damaged ads forgotten.")
        return

    ads = conn.execute("""
        SELECT source, source_listing_id, MAX(source_url) AS url, MAX(vin) AS vin, MAX(title) AS title
        FROM listing_observations
        WHERE removed_at IS NULL AND excluded_reason IS NULL
          AND source_url IS NOT NULL AND source_listing_id IS NOT NULL
        GROUP BY source, source_listing_id
    """).fetchall()
    print(f"Checking {len(ads)} ads still online...")

    damaged, unreadable = [], 0
    for i, ad in enumerate(ads, 1):
        try:
            detail = fetch_detail(ad["url"]) or {}
        except Exception as e:
            print(f"  [error] {ad['url']}: {_safe(str(e))}")
            detail = {}
        if "damaged" not in detail:
            unreadable += 1
        elif detail["damaged"]:
            damaged.append(ad)
            print(f"  [damaged] {ad['source']} {ad['vin']} {_safe(ad['title'] or '')} {ad['url']}")
            if "--yes" in sys.argv:
                conn.execute("INSERT OR IGNORE INTO damaged_listings (source, source_listing_id) VALUES (?, ?)",
                             (ad["source"], ad["source_listing_id"]))
                conn.commit()
        if i % 50 == 0:
            print(f"  ... {i}/{len(ads)}, {len(damaged)} damaged, {unreadable} unreadable", flush=True)
        time.sleep(DELAY_S)

    print(f"\n{len(damaged)} damaged out of {len(ads)} ads ({unreadable} could not be read).")
    print("Recorded." if "--yes" in sys.argv else "Nothing changed. Run with --yes to record them.")


if __name__ == "__main__":
    main()
