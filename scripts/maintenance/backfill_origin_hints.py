"""Give the cars already in the database their North American equipment hint (migration 33), from the
descriptions of their live ads: a car whose ads list a satellite tuner, the VIN label under the
windscreen or a US/Canadian country version then waits on the Weryfikacja page for its origin market.
New ads get theirs when approved (webapp/services/listings.py).

Reads pending_listings once (one pass over its descriptions). Cars with a hint already, or with an
origin a person decided, are left as they are.

Usage: python scripts/maintenance/backfill_origin_hints.py [--dry-run] [--yes]
Writes to the backend selected by DB_BACKEND (d1 = production) after confirmation.
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
import db
from validation import OVERSEAS_ORIGINS, north_american_equipment


def hints(conn):
    """{vin: (market, why)} for the cars to update, and the car rows by VIN."""
    cars = {r["vin"]: r for r in conn.execute("""
        SELECT vin, car_id, make, model, origin_market FROM vehicles
        WHERE origin_hint_market IS NULL AND origin_checked_at IS NULL""")}
    found = {}
    for ad in conn.execute("""SELECT vin, raw_description FROM pending_listings
                              WHERE status IN ('approved', 'pending') AND vin IS NOT NULL ORDER BY id"""):
        if ad["vin"] not in cars:
            continue
        market, reasons = north_american_equipment(ad["raw_description"])
        if market:   # the newest ad with such equipment wins, as on approval
            found[ad["vin"]] = (market, "Kody wyposażenia z ogłoszenia: " + "; ".join(reasons))
    return found, cars


def main():
    dry = "--dry-run" in sys.argv
    conn = db.get_db()
    found, cars = hints(conn)
    flagged = [v for v in found if cars[v]["origin_market"] not in OVERSEAS_ORIGINS]
    print(f"Auta z wyposażeniem z Ameryki Północnej: {len(found)}, "
          f"z tego bez rynku z Ameryki (trafią do Weryfikacji): {len(flagged)}")
    print("Rynek w bazie:", dict(Counter(cars[v]["origin_market"] or "—" for v in flagged)))
    for vin in flagged[:40]:
        c = cars[vin]
        print(f"  #{c['car_id']} {c['make']} {c['model']} {vin} [{c['origin_market'] or '—'}] {found[vin][1]}")
    if dry or not found:
        conn.close()
        return
    if "--yes" not in sys.argv and input(f"Zapisać podpowiedź dla {len(found)} aut? [t/N] ").strip().lower() != "t":
        conn.close()
        return
    for vin, (market, why) in found.items():
        conn.execute("UPDATE vehicles SET origin_hint_market = ?, origin_hint = ? WHERE vin = ? AND origin_hint_market IS NULL",
                     (market, why, vin))
    conn.commit()
    conn.close()
    print("Zapisano.")


if __name__ == "__main__":
    main()
