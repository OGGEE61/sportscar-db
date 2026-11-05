"""Fetch the full gallery for otomoto listings stored with a single photo.

Listings first seen before 2026-10-12 kept only the list-page thumbnail, and known listings skip
the detail page, so scraper runs never add the rest. This works only while the ad is still online.

Usage: python scripts/maintenance/backfill_otomoto_photos.py [--dry-run] [--yes]
Writes to the backend selected by DB_BACKEND (d1 = production) after confirmation.
"""
import json
import os
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
import db
from scripts.detect_plates import fetch_listing_gallery_photos


def main():
    dry_run = "--dry-run" in sys.argv
    conn = db.get_db()
    rows = conn.execute("""
        SELECT p.id, p.source_url FROM pending_listings p
        WHERE p.source = 'otomoto' AND p.status = 'approved'
          AND p.source_url IS NOT NULL AND p.source_url != ''
          AND (p.photos IS NULL OR p.photos NOT LIKE '%,%')
          AND EXISTS (SELECT 1 FROM listing_observations o
                      WHERE o.source = p.source AND o.source_listing_id = p.source_listing_id AND o.removed_at IS NULL)
        ORDER BY p.id DESC
    """).fetchall()
    print(f"{len(rows)} live otomoto listing(s) with at most one photo")

    found = {}
    outcome = Counter()
    for r in rows:
        gallery = fetch_listing_gallery_photos(r["source_url"])[:10]
        if len(gallery) > 1:
            found[r["id"]] = gallery
            outcome["gallery found"] += 1
        else:
            outcome["ad gone or no gallery"] += 1
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
        if input(f"Store galleries on {len(found)} listing(s) in {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted, nothing changed.")

    for listing_id, gallery in found.items():
        conn.execute("UPDATE pending_listings SET photos = ? WHERE id = ?", (json.dumps(gallery), listing_id))
    conn.commit()
    conn.close()
    print(f"Stored galleries on {len(found)} listing(s)")


if __name__ == "__main__":
    main()
