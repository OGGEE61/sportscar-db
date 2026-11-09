"""Reveal missing VINs and registration plates of Otomoto listings, from this machine.

Otomoto blocks reveals from GitHub's runners after a burst (HTTP 403), but answers a normal
connection. This fills in, at the scraper's pace (base_scraper.VIN_REVEAL_DELAY_S), and stops at
the first 403:
  1. VINs of pending Otomoto listings whose ad has a VIN that the scraper could not reveal.
     A VIN is stored only if it passes validation.is_plausible_vin, the same check the scraper uses.
  2. Plates of pending and approved Otomoto listings scraped since PLATES_HIDDEN_SINCE (from then on
     the plate is no longer in the ad page). An approved listing's car gets the plate too, if it
     has none. Ads that otomoto answers without a plate are listed in NO_PLATE_FILE and not asked
     again.
Nothing is approved, rejected or deleted.

Needs a logged-in scrapers/otomoto_cookies.json. Runs every few hours on the Mac through launchd:
see scripts/launchd/README.md. Each run writes one line to the run log.

Usage: python scripts/maintenance/reveal_pending_vins.py [--limit N]   (N per step)

Writes against the backend selected by DB_BACKEND (d1 = production).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
import base_scraper
from base_scraper import _log_run, check_session, load_cookies, refresh_session, reveal_plate, reveal_vin
from db import get_db
from validation import is_plausible_vin

# Otomoto's id_token lasts 15 minutes; a longer run needs a fresh one
TOKEN_REFRESH_S = 10 * 60
PLATES_HIDDEN_SINCE = "2026-11-05"
# Otomoto listing ids answered without a plate, one per line (local to this machine, not in git)
NO_PLATE_FILE = os.path.join(ROOT, "logs", "no_plate_ads.log")


def _read_no_plate() -> set:
    try:
        with open(NO_PLATE_FILE) as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def _add_no_plate(listing_id: str):
    os.makedirs(os.path.dirname(NO_PLATE_FILE), exist_ok=True)
    with open(NO_PLATE_FILE, "a") as f:
        f.write(f"{listing_id}\n")


class _Session:
    """Logged-in cookies, refreshed before the id_token expires."""

    def __init__(self):
        self.cookies = refresh_session(load_cookies(), log_errors=False)
        self.at = time.monotonic()

    def get(self):
        if time.monotonic() - self.at > TOKEN_REFRESH_S:
            self.cookies = refresh_session(self.cookies, log_errors=False)
            self.at = time.monotonic()
        return self.cookies


def fill_vins(conn, session, limit=None) -> tuple:
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
            print("Stopped: Otomoto blocked the reveals (HTTP 403 or masked VINs).")
            break
        vin = reveal_vin(r["source_listing_id"], session.get())
        if vin and is_plausible_vin(vin):
            conn.execute("UPDATE pending_listings SET vin = ? WHERE id = ? AND (vin IS NULL OR vin = '')",
                         (vin, r["id"]))
            conn.commit()
            found += 1
            outcome = "VIN"
        else:
            outcome = "implausible VIN, not stored" if vin else "no VIN"
        print(f"  [{i}/{len(rows)}] {r['variant']} {r['source_listing_id']}: {outcome}", flush=True)
    return found, len(rows)


def fill_plates(conn, session, limit=None) -> tuple:
    no_plate = _read_no_plate()
    rows = conn.execute("""
        SELECT id, source_listing_id, variant, status, vin FROM pending_listings
        WHERE source = 'otomoto' AND status IN ('pending', 'approved')
          AND COALESCE(registration_plate, '') = '' AND scraped_at >= ?
        ORDER BY id DESC
    """, (PLATES_HIDDEN_SINCE,)).fetchall()
    rows = [r for r in rows if str(r["source_listing_id"]) not in no_plate]
    rows = rows[:limit] if limit else rows
    print(f"{len(rows)} Otomoto listings without a plate since {PLATES_HIDDEN_SINCE}.")
    found = 0
    for i, r in enumerate(rows, 1):
        if not base_scraper.plate_reveal_allowed():
            print("Stopped: Otomoto blocked the reveals (HTTP 403).")
            break
        plate = reveal_plate(r["source_listing_id"], session.get())
        if plate:
            conn.execute("UPDATE pending_listings SET registration_plate = ? "
                         "WHERE id = ? AND COALESCE(registration_plate, '') = ''", (plate, r["id"]))
            if r["status"] == "approved" and r["vin"]:
                conn.execute("UPDATE vehicles SET registration_plate = ? "
                             "WHERE vin = ? AND COALESCE(registration_plate, '') = ''", (plate, r["vin"]))
            conn.commit()
            found += 1
            outcome = "plate"
        elif plate == "":
            _add_no_plate(str(r["source_listing_id"]))
            outcome = "no plate in the ad"
        else:
            outcome = "request failed"
        print(f"  [{i}/{len(rows)}] {r['variant']} {r['source_listing_id']}: {outcome}", flush=True)
    return found, len(rows)


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    session = _Session()
    if not check_session(session.cookies):
        _log_run("error", "VIN backfill: not logged in to Otomoto, update scrapers/otomoto_cookies.json on the Mac.",
                 source="otomoto")
        sys.exit("Not logged in to Otomoto: update scrapers/otomoto_cookies.json first.")
    # The per-run caps are for the scheduled scrapes; here the pace and the stop on 403 are enough
    base_scraper.VIN_REVEALS_PER_RUN = 10 ** 6

    conn = get_db()
    vins, vin_rows = fill_vins(conn, session, limit)
    plates, plate_rows = fill_plates(conn, session, limit)
    blocked = base_scraper._vin_reveals["blocked"] or base_scraper._vin_reveals["vins_masked"]
    print(f"Done: {vins} VINs and {plates} plates filled in.")
    if not (vin_rows or plate_rows):
        return
    _log_run("partial" if blocked else "success",
             f"VIN backfill: {vins} of {vin_rows} pending Otomoto listings got a VIN, "
             f"{plates} of {plate_rows} got a plate"
             + (" (stopped: Otomoto blocked or masked the reveals)." if blocked else "."),
             processed=vins + plates, source="otomoto")


if __name__ == "__main__":
    main()
