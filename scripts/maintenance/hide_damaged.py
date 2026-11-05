"""Hide stored listings that their site marks as damaged.

The scrapers skip damaged cars (detail["damaged"]); this applies the same check to ads already
stored by opening every ad that is still online. Matching listing_observations get
excluded_reason = 'damaged': the rows and VINs stay (the car remains known) and the dashboard,
model analytics and /vehicles skip them. Only that ad is hidden, so the same car in another,
undamaged ad stays visible. Ads no longer online can't be checked and are left as they are.

Usage: python scripts/maintenance/hide_damaged.py [--yes] [--undo]

  (no flag)  list what would be hidden, change nothing
  --yes      hide them
  --undo     show the listings hidden as damaged again

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
        conn.execute("UPDATE listing_observations SET excluded_reason = NULL WHERE excluded_reason = 'damaged'")
        conn.commit()
        print("Listings hidden as damaged are visible again.")
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
        if i % 50 == 0:
            print(f"  ... {i}/{len(ads)}, {len(damaged)} damaged, {unreadable} unreadable", flush=True)
        time.sleep(DELAY_S)

    print(f"\n{len(damaged)} damaged out of {len(ads)} ads ({unreadable} could not be read).")
    if "--yes" not in sys.argv:
        print("Nothing changed. Run with --yes to hide them.")
        return
    for ad in damaged:
        conn.execute("UPDATE listing_observations SET excluded_reason = 'damaged' "
                     "WHERE source = ? AND source_listing_id = ?", (ad["source"], ad["source_listing_id"]))
    conn.commit()
    print(f"Hidden: {len(damaged)} ads.")


if __name__ == "__main__":
    main()
