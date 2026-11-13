"""Look at rejected listings again: is the ad still up, and can its VIN be had now?

A rejected listing is never looked at again by the scrapers. Most were rejected for a missing
VIN, but sellers add VINs later, a VIN can sit behind otomoto's "Show VIN", and a few were rejected
by a bulk button by mistake. This opens each rejected listing's page:
  - gone (410 / 404): is_listing_active = 0;
  - up: is_listing_active = 1, the page is read again (VIN, plate, first registration, specs), and
    the listing goes back to pending when it now passes its scraper's rules
    (scripts/maintenance/audit_listings.py) and has a VIN, or one behind "Show VIN" (the reveal job
    gets it).
Only listings rejected without a stated reason, or for a missing VIN, are restored: a rejection
with its own note (a wrong model, a damaged car) stands. Nothing is approved or deleted.

Dry run by default (a report only); --apply writes. Pages are opened at the scrapers' pace.

Usage: python scripts/maintenance/recheck_rejected.py [--source otomoto|olx|autoplac] [--limit N] [--apply]
Reads the backend selected by DB_BACKEND (d1 = production).
"""
import contextlib
import io
import os
import random
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
from base_scraper import fetch_listing  # noqa: E402
from validation import is_plausible_vin, is_valid_registration_plate  # noqa: E402

from scripts.maintenance.audit_listings import audit, load_configs  # noqa: E402

PAUSE_S = (3.0, 6.0)
VIN_REASONS = ("Missing/Invalid VIN",)


def restorable_reason(note) -> bool:
    """Rejected without a stated reason (a bulk button) or for a missing VIN."""
    return not (note or "").strip() or (note or "").startswith(VIN_REASONS)


def refreshed(listing: dict, detail: dict) -> dict:
    """The listing with what its page says now (only fields the page gives)."""
    out = dict(listing)
    for key in ("year", "mileage_km", "power_hp", "engine_cc", "fuel_type", "body_type", "raw_description"):
        if detail.get(key):
            out[key] = detail[key]
    if detail.get("price_from_detail"):
        out["price_pln"] = detail["price_from_detail"]
    if is_plausible_vin(detail.get("vin") or ""):
        out["vin"] = detail["vin"]
    if detail.get("vin_confidence"):
        out["vin_confidence"] = detail["vin_confidence"]
    plate = detail.get("registration_plate")
    if plate and is_valid_registration_plate(plate) and not out.get("registration_plate"):
        out["registration_plate"] = plate
    if detail.get("first_registration_date") and not out.get("first_registration_date"):
        out["first_registration_date"] = detail["first_registration_date"]
    return out


def decide(listing: dict, state: str, detail: dict, configs: dict) -> dict:
    """{"state", "action": "restore" | "keep" | "gone" | "error", "why", "listing"} for one listing."""
    if state != "active":
        return {"state": state, "action": state, "why": "", "listing": listing}
    now = refreshed(listing, detail)
    a = audit(dict(now, status="rejected"), configs)
    vin = "stored" if is_plausible_vin(now.get("vin") or "") else a["vin"]
    if not restorable_reason(listing.get("review_notes")):
        return {"state": state, "action": "keep", "why": f"odrzucone z powodem: {listing['review_notes'][:50]}", "listing": now}
    if a["broken"]:
        return {"state": state, "action": "keep", "why": "; ".join(a["broken"])[:90], "listing": now}
    if vin in ("stored", "in_description", "behind_reveal"):
        return {"state": state, "action": "restore", "why": f"VIN: {vin}", "listing": now}
    return {"state": state, "action": "keep", "why": "nadal bez VIN-u", "listing": now}


def write(conn, d: dict):
    listing = d["listing"]
    if d["state"] in ("active", "gone"):
        conn.execute("UPDATE pending_listings SET is_listing_active = ?, checked_at = datetime('now') WHERE id = ?",
                     (1 if d["state"] == "active" else 0, listing["id"]))
    if d["action"] == "restore":
        conn.execute("""UPDATE pending_listings
                        SET status = 'pending', reviewed_at = NULL, review_notes = NULL,
                            vin = ?, vin_confidence = ?, registration_plate = ?, first_registration_date = ?,
                            year = ?, mileage_km = ?, power_hp = ?, engine_cc = ?, price_pln = ?
                        WHERE id = ? AND status = 'rejected'""",
                     (listing.get("vin"), listing.get("vin_confidence"), listing.get("registration_plate"),
                      listing.get("first_registration_date"), listing.get("year"), listing.get("mileage_km"),
                      listing.get("power_hp"), listing.get("engine_cc"), listing.get("price_pln"), listing["id"]))
    conn.commit()


def main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    import db

    apply = "--apply" in sys.argv
    source = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else None
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    with contextlib.redirect_stdout(io.StringIO()):
        configs = load_configs()
    conn = db.get_db()
    sql = ("SELECT * FROM pending_listings WHERE status = 'rejected' AND source_url IS NOT NULL"
           + (" AND source = ?" if source else "") + " ORDER BY id DESC" + (f" LIMIT {int(limit)}" if limit else ""))
    rows = [dict(r) for r in conn.execute(sql, (source,) if source else ()).fetchall()]
    print(f"Odrzucone do sprawdzenia: {len(rows)}" + ("" if apply else " (na sucho: nic nie zapisuję)"))

    tally, restored = Counter(), []
    for i, listing in enumerate(rows, 1):
        with contextlib.redirect_stdout(io.StringIO()):
            state, detail = fetch_listing(listing["source_url"])
        d = decide(listing, state, detail, configs)
        tally[d["action"]] += 1
        print(f"[{i}/{len(rows)}] {listing['id']} {listing['source']} {listing.get('variant') or ''}: "
              f"{d['action']}" + (f" ({d['why']})" if d["why"] else ""), flush=True)
        if d["action"] == "restore":
            restored.append(listing["id"])
        if apply:
            write(conn, d)
        time.sleep(random.uniform(*PAUSE_S))
    conn.close()

    print(f"\nWynik: {len(restored)} wraca do Kolejki, {tally['keep']} zostaje odrzuconych (aktywne), "
          f"{tally['gone']} zniknęło z portalu, {tally['error']} nie dało się sprawdzić.")
    if restored:
        print("Do Kolejki: " + ", ".join(map(str, restored)))
    if not apply:
        print("Nic nie zapisano. Z --apply: zapis stanu ogłoszeń i przywrócenie powyższych.")


if __name__ == "__main__":
    main()
