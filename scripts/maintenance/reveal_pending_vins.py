"""Reveal missing VINs and registration plates of Otomoto listings, a batch per run.

The scheduled scrapes spend their reveals in listing order, so a run can use them up before it
reaches a model and leave its new listings without a VIN. This job works only on what is still
missing, at the scraper's pace (base_scraper.VIN_REVEAL_DELAY_S), up to VIN_REVEALS_PER_RUN VINs
and as many plates per run, newest first, and stops at the first 403:
  1. VINs of pending Otomoto listings whose ad has a VIN that the scraper could not reveal.
  2. Plates of pending and approved Otomoto listings scraped since PLATES_HIDDEN_SINCE (from then on
     the plate is no longer in the ad page). An approved listing's car gets the plate too.
The listings come from the app (/api/reveal_queue) and the results go back to it
(/api/reveal_result), which stores a VIN only if it passes is_plausible_vin and a plate only if it
passes is_valid_registration_plate. Nothing is approved, rejected or deleted.

An ad that answered without a VIN is not asked again for VIN_RETRY_AFTER_S, one without a plate for
PLATE_RETRY_AFTER_S, so the batch moves on through the queue; STATE_FILE remembers them.

Runs on the VPS every 2 hours (deploy/scrapers/crontab). Needs a logged-in
scrapers/otomoto_cookies.json, and BASE_URL + API_TOKEN like the scrapers. Writes one line to the
run log.

Usage: python scripts/maintenance/reveal_pending_vins.py [--limit N]   (N per step, default 20)
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
import base_scraper
from base_scraper import (API_BASE, API_HEADERS, _API_SESSION, _log_run, _safe, check_session,
                          load_cookies, refresh_session, reveal_plate, reveal_vin)

# Otomoto's id_token lasts 15 minutes; a longer run needs a fresh one
TOKEN_REFRESH_S = 10 * 60
PLATES_HIDDEN_SINCE = "2026-11-05"
VIN_RETRY_AFTER_S = 24 * 3600
PLATE_RETRY_AFTER_S = 7 * 24 * 3600
# {"vin": {listing_id: unix time of an answer without one}, "plate": {...}}; on the VPS a mounted
# directory (deploy/scrapers/compose.yml), so it outlives the container
STATE_FILE = os.environ.get("REVEAL_STATE_FILE") or os.path.join(ROOT, "logs", "reveal_state.json")


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    return {"vin": dict(state.get("vin") or {}), "plate": dict(state.get("plate") or {})}


def save_state(state: dict):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except OSError as e:
        print(f"[state] not saved ({_safe(str(e))[:120]}): the same ads will be asked again next run")


def due(items: list, tried: dict, retry_after_s: float, now: float) -> list:
    """Items not answered empty within retry_after_s; drops entries that are past it."""
    for sid, at in list(tried.items()):
        if now - at >= retry_after_s:
            del tried[sid]
    return [it for it in items if it["source_listing_id"] not in tried]


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


def fill_vins(items: list, session, tried: dict) -> int:
    found = 0
    for i, it in enumerate(items, 1):
        if not base_scraper.vin_reveal_allowed():
            print("VINs stopped: per-run limit reached, or Otomoto blocked/masked the reveals.")
            break
        vin = reveal_vin(it["source_listing_id"], session.get())
        if vin and send_result(it["id"], vin=vin).get("vin"):
            found += 1
            outcome = f"VIN {vin}"
        elif vin:
            outcome = f"VIN {vin} not stored (rejected by the validator)"
            tried[it["source_listing_id"]] = time.time()
        else:
            outcome = "no VIN"
            if not (base_scraper._vin_reveals["blocked"] or base_scraper._vin_reveals["vins_masked"]):
                tried[it["source_listing_id"]] = time.time()
        print(f"  [vin {i}/{len(items)}] {it['variant']} {it['source_listing_id']}: {outcome}", flush=True)
    return found


def fill_plates(items: list, session, tried: dict) -> int:
    found = 0
    for i, it in enumerate(items, 1):
        if not base_scraper.plate_reveal_allowed():
            print("Plates stopped: per-run limit reached, or Otomoto blocked the reveals.")
            break
        plate = reveal_plate(it["source_listing_id"], session.get())
        if plate and send_result(it["id"], plate=plate).get("plate"):
            found += 1
            outcome = f"plate {plate}"
        elif plate == "":
            tried[it["source_listing_id"]] = time.time()
            outcome = "no plate in the ad"
        elif plate:
            outcome = f"plate {plate} not stored"
        else:
            outcome = "request failed"
        print(f"  [plate {i}/{len(items)}] {it['variant']} {it['source_listing_id']}: {outcome}", flush=True)
    return found


def main():
    if "--limit" in sys.argv:
        base_scraper.VIN_REVEALS_PER_RUN = int(sys.argv[sys.argv.index("--limit") + 1])
    batch = base_scraper.VIN_REVEALS_PER_RUN

    queue = fetch_queue()
    state, now = load_state(), time.time()
    vin_items = due(queue.get("vins", []), state["vin"], VIN_RETRY_AFTER_S, now)
    plate_items = due(queue.get("plates", []), state["plate"], PLATE_RETRY_AFTER_S, now)
    print(f"Queue: {len(vin_items)} VINs and {len(plate_items)} plates to reveal "
          f"(of {len(queue.get('vins', []))} and {len(queue.get('plates', []))}); "
          f"this run takes up to {batch} of each.")
    if not (vin_items or plate_items):
        save_state(state)
        return

    session = _Session()
    if not check_session(session.cookies):
        _log_run("error", "VIN backfill: not logged in to Otomoto, update the Otomoto cookies.", source="otomoto")
        sys.exit("Not logged in to Otomoto: update the cookies first.")

    vins = fill_vins(vin_items[:batch], session, state["vin"])
    plates = fill_plates(plate_items[:batch], session, state["plate"])
    save_state(state)
    blocked = base_scraper._vin_reveals["blocked"] or base_scraper._vin_reveals["vins_masked"]
    print(f"Done: {vins} VINs and {plates} plates filled in.")
    _log_run("partial" if blocked else "success",
             f"VIN backfill: {vins} of {min(len(vin_items), batch)} pending Otomoto listings got a VIN, "
             f"{plates} of {min(len(plate_items), batch)} got a plate "
             f"(queue: {len(vin_items)} VINs, {len(plate_items)} plates)"
             + (" (stopped: Otomoto blocked or masked the reveals)." if blocked else "."),
             processed=vins + plates, source="otomoto")


if __name__ == "__main__":
    main()
