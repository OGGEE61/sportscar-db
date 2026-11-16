"""Fetch CEPiK reports for cars that lack one, through the app's API. Runs on the VPS.

scripts/fetch_cepik.py does the same against the database directly, which needs the D1
credentials; the VPS has only BASE_URL + API_TOKEN, like the scrapers. So the cars come from the
app (/api/cepik_queue), CEPiK (moj.gov.pl) is asked from here, and each answer goes back to the
app (/api/cepik_result), which saves the report, or sends the plate back to /plates when CEPiK
does not know the VIN + plate, or notes a failed lookup for the next run.

moj.gov.pl has hours when every request times out: after STOP_AFTER_FAILED lookups in a row
that got no answer the run stops, and the next run takes those cars up again.

Runs nightly (deploy/scrapers/crontab). Writes one line to the run log.

Usage: python scripts/maintenance/cepik_remote.py [--limit N]   (default 60 cars)
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
from base_scraper import API_BASE, API_HEADERS, _API_SESSION, _log_run, _safe
from scripts.fetch_cepik import CepikClient

PAUSE_S = 2.0            # between cars, as the local run
STOP_AFTER_FAILED = 5    # lookups in a row without an answer from moj.gov.pl


def fetch_queue(limit: int) -> list:
    r = _API_SESSION.post(f"{API_BASE}/api/cepik_queue", json={"limit": limit}, headers=API_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["cars"]


def send_result(car: dict, report, http_status) -> str:
    """The app's outcome: 'saved', 'reverted' / 'queued' (plate back to /plates), 'error'."""
    try:
        r = _API_SESSION.post(f"{API_BASE}/api/cepik_result", headers=API_HEADERS, timeout=30,
                              json={"vin": car["vin"], "plate": car["plate"], "report": report, "http_status": http_status})
        r.raise_for_status()
        return r.json().get("outcome", "error")
    except Exception as e:
        print(f"    [api] result not stored: {_safe(str(e))[:120]}")
        return "not_stored"


def run(limit: int, client=None, pause: float = PAUSE_S) -> dict:
    client = client or CepikClient()
    cars = fetch_queue(limit)
    counts = {"cars": len(cars), "saved": 0, "not_found": 0, "failed": 0, "stopped": False}
    print(f"CEPiK: {len(cars)} cars to check")
    in_a_row = 0
    for i, car in enumerate(cars, 1):
        print(f"[{i}/{len(cars)}] {car['make']} {car['model']} {car['vin']}")
        report = client.fetch_vehicle_data(car["vin"], car["plate"], car["first_registration_date"])
        status = getattr(client, "last_status", None)
        outcome = send_result(car, report, status)
        if outcome == "saved":
            counts["saved"] += 1
        elif outcome in ("reverted", "queued"):
            counts["not_found"] += 1
        else:
            counts["failed"] += 1
        # No HTTP status at all: moj.gov.pl did not answer (a timeout), unlike a 404 or a bad date
        in_a_row = in_a_row + 1 if (report is None and status is None) else 0
        print(f"    {outcome}")
        if in_a_row >= STOP_AFTER_FAILED:
            counts["stopped"] = True
            print(f"moj.gov.pl did not answer {in_a_row} times in a row: stopping, the next run continues")
            break
        if i < len(cars):
            time.sleep(pause)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CEPiK reports for cars without one, through the app's API")
    parser.add_argument("--limit", type=int, default=60)
    c = run(parser.parse_args().limit)
    message = (f"CEPiK: {c['saved']} raportów zapisanych, {c['not_found']} nieznanych w CEPiK (tablice do /plates), "
               f"{c['failed']} bez odpowiedzi" + (", przerwano: moj.gov.pl nie odpowiada" if c["stopped"] else "")
               + f" (z {c['cars']} w kolejce)")
    print(message)
    _log_run("warning" if c["stopped"] else "success", message, processed=c["saved"], source="cepik")
