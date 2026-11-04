"""Przelicza flagę cofniętego licznika dla wszystkich raportów CEPiK wg aktualnego progu.

Użycie (domyślnie dry-run, bez zapisu):
    DB_BACKEND=d1 python scripts/maintenance/recompute_odometer_rollback.py
    DB_BACKEND=d1 python scripts/maintenance/recompute_odometer_rollback.py --apply
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

import db
from scripts.fetch_cepik import detect_rollback, ROLLBACK_MIN_DIFF_KM

ROLLBACK_TAG = "Cofnięty licznik%"


def main(apply: bool) -> None:
    conn = db.get_db()  # D1 gdy DB_BACKEND=d1 (get_conn() to zawsze lokalny SQLite)
    rows = conn.execute(
        "SELECT vin, last_odometer_km, odometer_rollback, rollback_diff_km FROM cepik_reports"
    ).fetchall()
    print(f"Raportów: {len(rows)}, próg: {ROLLBACK_MIN_DIFF_KM} km, tryb: {'APPLY' if apply else 'dry-run'}")

    cleared = set_ = 0
    for r in rows:
        vin, last_km, old_flag, old_diff = r[0], r[1], r[2], r[3]
        flag, diff, listing_km = detect_rollback(conn, vin, last_km)
        if flag == (old_flag or 0) and diff == (old_diff or 0):
            continue
        print(f"  {vin}: flaga {old_flag}->{flag}, różnica {old_diff}->{diff} (SKP {last_km}, ogł. {listing_km})")
        if flag:
            set_ += 1
        else:
            cleared += 1
        if apply:
            conn.execute(
                "UPDATE cepik_reports SET odometer_rollback = ?, rollback_diff_km = ? WHERE vin = ?",
                (flag, diff, vin),
            )
            if flag:
                conn.execute(
                    "INSERT OR REPLACE INTO tags (vin, tag, source_method) VALUES (?, ?, 'cepik')",
                    (vin, f"Cofnięty licznik (SKP: {last_km} km / Ad: {listing_km} km)"),
                )
            else:
                conn.execute(
                    "DELETE FROM tags WHERE vin = ? AND source_method = 'cepik' AND tag LIKE ?",
                    (vin, ROLLBACK_TAG),
                )
    if apply:
        conn.commit()
    print(f"Zmiany: zdjęto flagę {cleared}, ustawiono/zaktualizowano {set_}")


if __name__ == "__main__":
    main("--apply" in sys.argv)
