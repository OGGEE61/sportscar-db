"""Send cars that CEPiK could not find (VIN + plate) back to /plates for a human check.

Covers cars already logged as not_found before the sync did this itself: same logic as
webapp/services/plates.py requeue_for_plate_check (a photo-read plate goes back to pending and
is cleared from the car; a listing plate gets a pending entry and stays until corrected).

Usage: python scripts/maintenance/requeue_cepik_not_found.py [--dry-run] [--yes]
Writes to the backend selected by DB_BACKEND (d1 = production) after confirmation.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv()
import db
from webapp.services.plates import requeue_for_plate_check


def main():
    conn = db.get_db()
    rows = conn.execute("""
        SELECT v.vin, v.registration_plate, EXISTS(
                   SELECT 1 FROM plate_review_queue q
                   WHERE q.vin = v.vin AND q.status = 'approved' AND q.reviewed_plate = v.registration_plate) AS from_photo
        FROM cepik_sync_log l
        JOIN vehicles v ON v.vin = l.vin
        WHERE l.status = 'not_found'
          AND v.vin NOT LIKE 'PLH%' AND v.vin NOT LIKE 'UNVERIFIED%'
          AND v.registration_plate IS NOT NULL AND v.registration_plate != ''
          AND v.vin NOT IN (SELECT vin FROM cepik_reports)
          AND v.vin NOT IN (SELECT vin FROM plate_review_queue WHERE status = 'pending')
    """).fetchall()
    photo = sum(1 for r in rows if r["from_photo"])
    print(f"{len(rows)} car(s) with a plate that CEPiK did not find: {photo} photo-read (back to pending, plate cleared), "
          f"{len(rows) - photo} from the listing (new pending entry, plate kept)")
    if "--dry-run" in sys.argv or not rows:
        conn.close()
        return

    backend = os.environ.get("DB_BACKEND", "sqlite").lower()
    target = "PRODUCTION (Cloudflare D1)" if backend == "d1" else f"local SQLite ({db.DB_PATH})"
    if "--yes" not in sys.argv:
        if not sys.stdin.isatty():
            sys.exit(f"Refusing to write to {target} non-interactively; pass --yes to confirm.")
        if input(f"Send {len(rows)} car(s) back to plate verification in {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted.")
    done = Counter(requeue_for_plate_check(conn, r["vin"], r["registration_plate"]) for r in rows)
    conn.close()
    print(dict(done))


if __name__ == "__main__":
    main()
