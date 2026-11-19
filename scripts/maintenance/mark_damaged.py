"""Record stored ads that their site marks as damaged.

New ads are recorded when scraped; this applies the same check to ads already stored, by opening
every ad that is still online. Nothing is hidden or deleted: the ad goes into damaged_listings, so
the car's VIN shows it was sold as damaged and its price is left out of the price charts and
averages. Ads no longer online can't be checked and are left as they are.

With --text it opens nothing: it applies validation.damage_in_text to the title and description
already stored for every ad, so ads scraped before a change to that check get marked too. Run it
after each such change. An ad whose mark was dismissed on the car's page stays dismissed.

Usage: python scripts/maintenance/mark_damaged.py [--text] [--yes] [--undo]

  (no flag)  list what would be recorded, change nothing
  --text     check the stored text instead of opening the ads
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
from validation import damage_in_text

DELAY_S = 1.0


def mark_by_text(conn):
    """Record the ads whose stored text offers the car as damaged (no request to any portal)."""
    known = {(r["source"], r["source_listing_id"]) for r in
             conn.execute("SELECT source, source_listing_id FROM damaged_listings").fetchall()}
    ads = conn.execute("""
        SELECT source, source_listing_id, vin, raw_title, raw_description, price_pln FROM pending_listings
        WHERE status != 'rejected' AND source_listing_id IS NOT NULL
    """).fetchall()
    found = [(ad, quote) for ad in ads if (ad["source"], ad["source_listing_id"]) not in known
             and (quote := damage_in_text(ad["raw_title"], ad["raw_description"]))]
    for ad, quote in found:
        print(f"  [damaged] {ad['source']} {ad['source_listing_id']} {ad['vin']} {ad['price_pln']}: {_safe(quote)[:100]}")
        if "--yes" in sys.argv:
            conn.execute("INSERT OR IGNORE INTO damaged_listings (source, source_listing_id, reason) VALUES (?, ?, ?)",
                         (ad["source"], ad["source_listing_id"], quote))
    conn.commit()
    print(f"\n{len(found)} more damaged ads of {len(ads)} checked.")
    print("Recorded." if "--yes" in sys.argv else "Nothing changed. Run with --yes to record them.")


def main():
    conn = get_db()
    if "--undo" in sys.argv:
        conn.execute("DELETE FROM damaged_listings")
        conn.commit()
        print("Recorded damaged ads forgotten.")
        return
    if "--text" in sys.argv:
        mark_by_text(conn)
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
                conn.execute("INSERT OR IGNORE INTO damaged_listings (source, source_listing_id, reason) VALUES (?, ?, 'portal')",
                             (ad["source"], ad["source_listing_id"]))
                conn.commit()
        if i % 50 == 0:
            print(f"  ... {i}/{len(ads)}, {len(damaged)} damaged, {unreadable} unreadable", flush=True)
        time.sleep(DELAY_S)

    print(f"\n{len(damaged)} damaged out of {len(ads)} ads ({unreadable} could not be read).")
    print("Recorded." if "--yes" in sys.argv else "Nothing changed. Run with --yes to record them.")


if __name__ == "__main__":
    main()
