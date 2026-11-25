"""Plate review queue helpers shared by the /plates API and the CEPiK sync."""
import json
import re
from collections import defaultdict
from itertools import chain, zip_longest

from validation import is_valid_first_registration_date
from webapp.services.plate_rules import plate_candidates

# Lookups CEPiK may get for one card: its likeliest plate and date pairs
MAX_LOOKUPS_PER_CARD = 6


def normalize_plate(plate):
    return re.sub(r"[^A-Z0-9]", "", (plate or "").upper())


_STORED_PLATE = "UPPER(REPLACE(REPLACE(registration_plate, ' ', ''), '-', ''))"


def clear_plate(conn, vin, listing_id, plate):
    """Remove `plate` from the listing, vehicle and observations (only where it matches,
    however it was formatted when stored) and mark the car as missing a plate."""
    plate = normalize_plate(plate)
    if not plate:
        return
    if listing_id:
        conn.execute(f"UPDATE pending_listings SET registration_plate=NULL WHERE id=? AND {_STORED_PLATE}=?", (listing_id, plate))
    if not vin:
        return
    conn.execute(f"UPDATE pending_listings SET registration_plate=NULL WHERE vin=? AND {_STORED_PLATE}=?", (vin, plate))
    conn.execute(f"""
        UPDATE vehicles
        SET registration_plate=NULL,
            vin_status = CASE WHEN vin LIKE 'UNVERIFIED%' THEN 'placeholder' ELSE 'unverified' END
        WHERE vin=? AND {_STORED_PLATE}=?
    """, (vin, plate))
    conn.execute(f"UPDATE listing_observations SET registration_plate=NULL WHERE vin=? AND {_STORED_PLATE}=?", (vin, plate))
    try:
        conn.execute("DELETE FROM tags WHERE vin=? AND tag IN ('photo extracted', 'AI extracted plate')", (vin,))
        conn.execute("INSERT OR IGNORE INTO tags (vin, tag, source_method) VALUES (?, 'missing plates', 'system')", (vin,))
    except Exception:
        pass


def approve_plate(conn, card_id, vin, listing_id, plate, tag="photo extracted"):
    """Mark a queue card approved and put its plate on the listing, vehicle and observations."""
    conn.execute("""
        UPDATE plate_review_queue
        SET status='approved', reviewed_plate=?, reviewed_at=datetime('now')
        WHERE id=?
    """, (plate, card_id))
    if listing_id:
        conn.execute("UPDATE pending_listings SET registration_plate=? WHERE id=?", (plate, listing_id))
    if vin:
        conn.execute("UPDATE pending_listings SET registration_plate=? WHERE vin=?", (plate, vin))
        conn.execute("""
            UPDATE vehicles
            SET registration_plate=?,
                vin_status = CASE WHEN vin LIKE 'UNVERIFIED%' THEN 'placeholder' ELSE 'verified' END
            WHERE vin=?
        """, (plate, vin))
        conn.execute("UPDATE listing_observations SET registration_plate=? WHERE vin=?", (plate, vin))
        try:
            conn.execute("DELETE FROM tags WHERE vin=? AND tag IN ('missing plates', 'Missing plates')", (vin,))
            conn.execute("INSERT OR IGNORE INTO tags (vin, tag, source_method) VALUES (?, ?, ?)", (vin, tag, tag.replace(" ", "-")))
        except Exception:
            pass
        allow_cepik_retry(conn, vin, plate)


def restore_plate(conn, vin, plate):
    """Undo a "wrong plate" review: put the plate back wherever the car has none."""
    conn.execute("UPDATE pending_listings SET registration_plate=? WHERE vin=? AND (registration_plate IS NULL OR registration_plate='')", (plate, vin))
    conn.execute("""
        UPDATE vehicles
        SET registration_plate=?,
            vin_status = CASE WHEN vin LIKE 'UNVERIFIED%' THEN 'placeholder' ELSE 'verified' END
        WHERE vin=? AND (registration_plate IS NULL OR registration_plate='')
    """, (plate, vin))
    conn.execute("UPDATE listing_observations SET registration_plate=? WHERE vin=? AND (registration_plate IS NULL OR registration_plate='')", (plate, vin))
    try:
        conn.execute("DELETE FROM tags WHERE vin=? AND tag IN ('missing plates', 'Missing plates')", (vin,))
    except Exception:
        pass


def requeue_for_plate_check(conn, vin, plate):
    """CEPiK did not find this VIN + plate: send the plate back to /plates for a human check.

    A plate read from a photo goes back to 'pending' and is cleared from the car (like Revert).
    A plate that came from the listing text has no queue entry, so one is created and the
    plate stays on the car until the reviewer corrects it.
    Returns "already_pending", "reverted" or "queued".
    """
    if conn.execute("SELECT 1 FROM plate_review_queue WHERE vin=? AND status='pending'", (vin,)).fetchone():
        return "already_pending"

    for cand in conn.execute(
            "SELECT * FROM plate_review_queue WHERE vin=? AND status='approved' ORDER BY id DESC", (vin,)).fetchall():
        if normalize_plate(cand["reviewed_plate"]) == normalize_plate(plate):
            conn.execute("UPDATE plate_review_queue SET status='pending', reviewed_plate=NULL, reviewed_at=NULL WHERE id=?",
                         (cand["id"],))
            clear_plate(conn, vin, cand["listing_id"], cand["reviewed_plate"])
            conn.commit()
            return "reverted"

    photo_url = None
    row = conn.execute("SELECT photos FROM pending_listings WHERE vin=? AND photos IS NOT NULL AND photos NOT IN ('', '[]') "
                       "ORDER BY id DESC LIMIT 1", (vin,)).fetchone()
    if row:
        try:
            photos = json.loads(row["photos"])
            photo_url = photos[0] if photos else None
        except (ValueError, TypeError):
            pass
    obs = conn.execute("SELECT source_url FROM listing_observations WHERE vin=? ORDER BY observed_at DESC, id DESC LIMIT 1",
                       (vin,)).fetchone()
    conn.execute("""INSERT INTO plate_review_queue (vin, source_url, photo_url, detected_plate, confidence, status)
                    VALUES (?, ?, ?, ?, 0, 'pending')""", (vin, obs["source_url"] if obs else None, photo_url, normalize_plate(plate)))
    conn.commit()
    return "queued"


def allow_cepik_retry(conn, vin, plate):
    """A reviewed plate that differs from the one CEPiK rejected deserves a new lookup
    (the sync skips cars logged as not_found; the log message names the rejected plate)."""
    try:
        conn.execute("DELETE FROM cepik_sync_log WHERE vin=? AND status='not_found' AND message NOT LIKE ?",
                     (vin, f"%tablica {normalize_plate(plate)}%"))
    except Exception:
        pass  # cepik_sync_log not created yet


# ── CEPiK checks of the pending cards (scripts/fetch_cepik.py, scripts/maintenance/cepik_remote.py) ──

def card_plates(reading, ad_plate) -> list:
    """Plates to ask CEPiK about for a card, likeliest first: what the Polish plate rules make of the
    photo reading and of the ad's plate, taken in turn. A plate that cannot be Polish is left out:
    CEPiK knows only cars registered in Poland."""
    plates = []
    for plate in chain.from_iterable(zip_longest(plate_candidates(reading), plate_candidates(ad_plate))):
        if plate and plate not in plates:
            plates.append(plate)
    return plates


def swapped_date(date: str):
    """The date with day and month swapped, for a date an ad may have written the other way round
    (2019-01-03 for 3 January or 1 March), or None when the swap is the same date, not a date, or
    the day is the 1st (most often an ad giving only the month)."""
    year, month, day = date.split("-")
    if day == "01" or day == month or int(day) > 12:
        return None
    swapped = f"{year}-{day}-{month}"
    return swapped if is_valid_first_registration_date(swapped) else None


def plate_check_plan(conn) -> dict:
    """For every pending /plates card ({card id: plan}): its car, the plates and first registration
    dates to try (the car's date first, then other dates its ads give), the pairs already asked and
    those still to ask, likeliest first, at most MAX_LOOKUPS_PER_CARD pairs in all. After the ads'
    dates come the same dates with day and month swapped, as the last guesses."""
    cards = conn.execute("""
        SELECT q.id, q.vin, q.listing_id, q.detected_plate, v.registration_plate AS car_plate, v.make, v.year,
               v.origin_market, v.first_registration_date AS car_date
        FROM plate_review_queue q JOIN vehicles v ON v.vin = q.vin
        WHERE q.status = 'pending' AND q.vin NOT LIKE 'PLH%' AND q.vin NOT LIKE 'UNVERIFIED%'
        ORDER BY q.id
    """).fetchall()
    ad_dates = defaultdict(list)
    for r in conn.execute("""
        SELECT vin, first_registration_date FROM pending_listings
        WHERE vin IN (SELECT vin FROM plate_review_queue WHERE status = 'pending') AND first_registration_date <> ''
        ORDER BY id DESC
    """):
        if is_valid_first_registration_date(r["first_registration_date"]) and r["first_registration_date"] not in ad_dates[r["vin"]]:
            ad_dates[r["vin"]].append(r["first_registration_date"])
    asked = defaultdict(set)
    for r in conn.execute("""
        SELECT vin, plate, first_registration_date FROM cepik_plate_checks
        WHERE vin IN (SELECT vin FROM plate_review_queue WHERE status = 'pending')
    """):
        asked[r["vin"]].add((r["plate"], r["first_registration_date"]))

    plan = {}
    for c in cards:
        car_date = c["car_date"] if is_valid_first_registration_date(c["car_date"]) else None
        dates = ([car_date] if car_date else []) + [d for d in ad_dates[c["vin"]] if d != car_date]
        plates = card_plates(c["detected_plate"], c["car_plate"])
        swaps = [s for s in map(swapped_date, dates) if s and s not in dates]
        pairs = sorted(((p, d, j >= len(dates), i + j, i) for i, p in enumerate(plates) for j, d in enumerate(dates + swaps)),
                       key=lambda pair: pair[2:])[:MAX_LOOKUPS_PER_CARD]
        pairs = [(p, d) for p, d, *_ in pairs]
        plan[c["id"]] = {**dict(c), "plates": plates, "dates": dates,
                         "asked": [pair for pair in pairs if pair in asked[c["vin"]]],
                         "todo": [pair for pair in pairs if pair not in asked[c["vin"]]]}
    return plan


def plate_check_tasks(conn, limit: int) -> list:
    """The next CEPiK lookups: every card's likeliest pair not asked yet, then every card's next one,
    so one night's budget reaches all cards before trying second guesses."""
    plans = list(plate_check_plan(conn).values())
    tasks = []
    for rank in range(MAX_LOOKUPS_PER_CARD):
        for card in plans:
            if rank < len(card["todo"]) and len(tasks) < limit:
                plate, date = card["todo"][rank]
                tasks.append({"card_id": card["id"], "vin": card["vin"], "plate": plate,
                              "first_registration_date": date})
    return tasks


def plate_card_hints(card: dict) -> list:
    """Why CEPiK may not find this car, for the /plates card (a plate_check_plan entry): which of
    plate, first registration date or registration in Poland looks wrong, and what the automatic
    checks did."""
    hints = []
    reading, ad_plate = normalize_plate(card["detected_plate"]), normalize_plate(card["car_plate"])
    year, dates, origin = card["year"], card["dates"], card["origin_market"]
    if ad_plate and not plate_candidates(ad_plate):
        hints.append(f"{ad_plate} nie ma formatu polskiej tablicy: auto może jeździć na tablicach zagranicznych "
                     "albo nie być zarejestrowane w Polsce, a wtedy CEPiK go nie zna.")
    elif reading and not ad_plate and not plate_candidates(reading):
        hints.append(f"Odczyt ze zdjęcia ({reading}) nie pasuje do polskiej tablicy: tablica zagraniczna albo nieczytelna.")
    if reading and ad_plate and reading != ad_plate:
        hints.append(f"Tablica z ogłoszenia ({ad_plate}) różni się od odczytu ze zdjęcia ({reading}).")
    if not dates:
        hints.append("Brak daty pierwszej rejestracji: bez niej CEPiK nie sprawdzi auta.")
    else:
        if len(dates) > 1:
            hints.append("Ogłoszenia podają różne daty pierwszej rejestracji: " + ", ".join(dates) + ".")
        first_year = int(dates[0][:4])
        if dates[0].endswith("-01-01"):
            hints.append(f"Data {dates[0]} to najpewniej sam rok z ogłoszenia: CEPiK wymaga dokładnej daty pierwszej rejestracji.")
        if year and first_year < year - 1:
            hints.append(f"Data pierwszej rejestracji ({dates[0]}) jest wcześniejsza niż rocznik auta ({year}).")
        elif year and first_year >= year + 2 and origin and origin != "Polska":
            hints.append(f"Auto sprowadzone ({origin}): data z ogłoszenia może być datą rejestracji w Polsce, "
                         "a CEPiK wymaga daty pierwszej rejestracji za granicą.")
    if card["todo"]:
        hints.append(f"Czeka na automatyczne sprawdzenie w CEPiK: {len(card['todo'])} "
                     f"{_pairs_word(len(card['todo']))} tablicy i daty.")
    elif card["asked"]:
        hints.append(f"Sprawdzono automatycznie w CEPiK {len(card['asked'])} {_pairs_word(len(card['asked']))} "
                     "tablicy i daty: bez wyniku.")
    return hints


def _pairs_word(n: int) -> str:
    return "kombinację" if n == 1 else "kombinacje" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "kombinacji"
