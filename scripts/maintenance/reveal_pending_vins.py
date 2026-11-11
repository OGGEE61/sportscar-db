"""Reveal missing VINs and registration plates of Otomoto listings, a few per run.

The scrapes reveal only what a new listing needs, within the shared limits (see the block above
base_scraper.VIN_REVEAL_DELAY_S), so some listings are left without a VIN or plate. This job works
only on those, at the scrapers' pace and within the same limits:
  1. VINs of pending Otomoto listings whose ad has a VIN behind "Show VIN".
  2. Plates of pending, then approved, Otomoto listings scraped since PLATES_HIDDEN_SINCE (from
     then on the plate is no longer in the ad page). An approved listing's car gets the plate too.
Newest first. The listings come from the app (/api/reveal_queue) and the results go back to it
(/api/reveal_result), which stores a VIN only if it passes is_plausible_vin and a plate only if it
passes is_valid_registration_plate. Nothing is approved, rejected or deleted.

Shares with the scrapes: the per-day limit, the pause after an HTTP 403 (no request at all is sent
while it lasts) and the list of ads that recently answered without a VIN or plate.

Runs on the VPS (deploy/scrapers/crontab). Needs a logged-in scrapers/otomoto_cookies.json, and
BASE_URL + API_TOKEN like the scrapers. Writes one line to the run log.

Usage: python scripts/maintenance/reveal_pending_vins.py [--limit N]   (N per kind, default
base_scraper.VIN_REVEALS_PER_RUN)
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
import base_scraper
from base_scraper import (API_BASE, API_HEADERS, _API_SESSION, _log_run, _safe, check_session,
                          load_cookies, recently_asked, refresh_session, reveal_plate,
                          reveal_skip_reason, reveal_vin)

# Otomoto's id_token lasts 15 minutes; a longer run needs a fresh one
TOKEN_REFRESH_S = 10 * 60
PLATES_HIDDEN_SINCE = "2026-11-05"


def fetch_queue() -> dict:
    r = _API_SESSION.post(f"{API_BASE}/api/reveal_queue", json={"plates_since": PLATES_HIDDEN_SINCE},
                          headers=API_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def send_result(listing_id: int, **found) -> dict:
    try:
        r = _API_SESSION.post(f"{API_BASE}/api/reveal_result", json={"id": listing_id, **found},
                              headers=API_HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [api] result not stored: {_safe(str(e))[:120]}")
        return {}


def due(kind: str, items: list) -> list:
    """Items whose ad did not recently answer without a VIN / plate (base_scraper.recently_asked)."""
    return [it for it in items if not recently_asked(kind, it["source_listing_id"])]


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


def fill_vins(items: list, session) -> tuple:
    """(VINs stored, why the batch stopped early or None)."""
    found = 0
    for i, it in enumerate(items, 1):
        if why := reveal_skip_reason("vin"):
            return found, why
        vin = reveal_vin(it["source_listing_id"], session.get())
        if vin and send_result(it["id"], vin=vin).get("vin"):
            found += 1
            outcome = f"VIN {vin}"
        elif vin:
            outcome = f"VIN {vin} not stored (rejected by the validator)"
            base_scraper.mark_none("vin", it["source_listing_id"])
        else:
            outcome = "no VIN"
        print(f"  [vin {i}/{len(items)}] {it['variant']} {it['source_listing_id']}: {outcome}", flush=True)
    return found, None


def fill_plates(items: list, session) -> tuple:
    """(plates stored, why the batch stopped early or None)."""
    found = 0
    for i, it in enumerate(items, 1):
        if why := reveal_skip_reason("plate"):
            return found, why
        plate = reveal_plate(it["source_listing_id"], session.get())
        if plate and send_result(it["id"], plate=plate).get("plate"):
            found += 1
            outcome = f"plate {plate}"
        elif plate == "":
            outcome = "no plate in the ad"
        elif plate:
            outcome = f"plate {plate} not stored"
        else:
            outcome = "request failed"
        print(f"  [plate {i}/{len(items)}] {it['variant']} {it['source_listing_id']}: {outcome}", flush=True)
    return found, None


def main():
    if "--limit" in sys.argv:
        base_scraper.VIN_REVEALS_PER_RUN = int(sys.argv[sys.argv.index("--limit") + 1])
    batch = base_scraper.VIN_REVEALS_PER_RUN

    # Blocked or over today's limit: not a single request, not even the login check
    vin_why, plate_why = reveal_skip_reason("vin"), reveal_skip_reason("plate")
    if vin_why and plate_why:
        print(f"Nothing revealed: {vin_why}" + (f"; plates: {plate_why}" if plate_why != vin_why else ""))
        return

    queue = fetch_queue()
    vin_items = [] if vin_why else due("vin", queue.get("vins", []))
    plate_items = [] if plate_why else due("plate", queue.get("plates", []))
    print(f"Queue: {len(vin_items)} VINs and {len(plate_items)} plates to reveal "
          f"(of {len(queue.get('vins', []))} and {len(queue.get('plates', []))}); "
          f"this run takes up to {batch} of each.")
    if not (vin_items or plate_items):
        return

    session = _Session()
    if not check_session(session.cookies):
        _log_run("error", "VIN backfill: not logged in to Otomoto, update the Otomoto cookies.", source="otomoto")
        sys.exit("Not logged in to Otomoto: update the cookies first.")

    vins, vin_stop = fill_vins(vin_items[:batch], session)
    plates, plate_stop = fill_plates(plate_items[:batch], session)
    stop = vin_stop or plate_stop
    blocked = base_scraper._vin_reveals["blocked"]
    print(f"Done: {vins} VINs and {plates} plates filled in." + (f" Stopped: {stop}." if stop else ""))
    _log_run("partial" if blocked else "success",
             f"VIN backfill: {vins} of {min(len(vin_items), batch)} pending Otomoto listings got a VIN, "
             f"{plates} of {min(len(plate_items), batch)} got a plate "
             f"(queue: {len(vin_items)} VINs, {len(plate_items)} plates)"
             + (" (stopped: Otomoto blocked the reveals, all reveals paused for 24 h)." if blocked
                else f" (stopped: {stop})." if stop else "."),
             processed=vins + plates, source="otomoto")


if __name__ == "__main__":
    main()
