"""Checking a car's data by hand: its plate, first registration date, origin market and damage, and the
"Dane sprawdzone" mark once all of it is checked. Shared by the car's page and the review MCP server
(scripts/review_mcp.py)."""
from datetime import datetime

from validation import is_valid_first_registration_date


def damage_marks(conn, vin):
    """The car's ads marked damaged: by the portal ('portal') or by their text ('text: <quote>'), and
    whether the user dismissed the mark."""
    return conn.execute("""
        SELECT DISTINCT d.source, d.source_listing_id, d.reason, d.dismissed
        FROM damaged_listings d JOIN listing_observations o
          ON o.source = d.source AND o.source_listing_id = d.source_listing_id
        WHERE o.vin = ?""", (vin,)).fetchall()


def set_damage_dismissed(conn, vin, dismissed):
    """dismissed: the car's ads are not damaged after all (a wrong match in the ad's text, a seller's
    mistake); False brings the marks back. The rows stay, so a later scrape of the same ad does not
    mark it again."""
    conn.execute("""
        UPDATE damaged_listings SET dismissed = ?
        WHERE EXISTS (SELECT 1 FROM listing_observations o WHERE o.vin = ?
                        AND o.source = damaged_listings.source
                        AND o.source_listing_id = damaged_listings.source_listing_id)""", (1 if dismissed else 0, vin))
    conn.commit()


def add_condition_report(conn, vin, *, report_date=None, mileage_km=None, accident_free=None, service_history=None,
                         condition_score=None, inspection_by=None, notes=None, country=None, photo=None,
                         source_method="manual"):
    """A condition report: an inspection, or (accident_free=0) a damage found in the car's history (a
    VIN check, an auction record), with the country and an optional photo (an R2 key)."""
    conn.execute("""
        INSERT INTO condition_reports
          (vin, report_date, mileage_km, accident_free, service_history,
           condition_score, inspection_by, notes, country, photo, source_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (vin, report_date or datetime.today().strftime("%Y-%m-%d"), mileage_km, accident_free, service_history,
          condition_score, inspection_by, notes, country, photo, source_method))
    conn.commit()


def set_first_registration_date(conn, vin, date):
    """Store the car's first registration date (the exact day, abroad for an import). The nightly
    CEPiK checks of its /plates card try it first. Returns an error message or None."""
    if not is_valid_first_registration_date(date):
        return "Niepoprawna data (RRRR-MM-DD, od 1980, nie z przyszłości)"
    cur = conn.execute("UPDATE vehicles SET first_registration_date = ?, updated_at = datetime('now') WHERE vin = ?",
                       (date, vin))
    conn.commit()
    return None if cur.rowcount else "Nie znaleziono auta"


def set_data_checked(conn, vin, checked):
    """Mark the car's data (plate, first registration date, origin, damage) as checked by hand, or
    take the mark back. Returns False when there is no such car."""
    cur = conn.execute("UPDATE vehicles SET data_checked_at = CASE WHEN ? THEN CURRENT_TIMESTAMP END WHERE vin = ?",
                       (1 if checked else 0, vin))
    conn.commit()
    return bool(cur.rowcount)


def cars_to_check(conn, limit, offset=0):
    """Cars with an approved ad whose data nobody has checked yet, newest first, and how many there are.
    Both read through idx_vehicles_unchecked, so a page costs about `limit` rows plus the count."""
    total = conn.execute("SELECT COUNT(*) FROM vehicles WHERE data_checked_at IS NULL").fetchone()[0]
    cars = conn.execute("""
        SELECT v.car_id, v.vin, v.make, v.model, v.variant, v.year, v.registration_plate, v.first_registration_date,
               v.origin_market, v.ai_suggested_market, v.ai_conflict, v.created_at
        FROM vehicles v
        WHERE v.data_checked_at IS NULL AND v.vin NOT LIKE 'PLH%' AND v.vin NOT LIKE 'UNVERIFIED%'
          AND EXISTS (SELECT 1 FROM pending_listings p WHERE p.vin = v.vin AND p.status = 'approved')
        ORDER BY v.created_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    return cars, total


# ── "Do sprawdzenia": cars a review left uncertain, for the user to check by hand ──

# What a note is about, as shown on the page
NOTE_TOPICS = {"plate": "Tablica", "date": "Data rejestracji", "damage": "Szkoda", "origin": "Pochodzenie",
               "vin": "VIN", "other": "Inne"}


def add_review_note(conn, vin, topic, note, ad_url=None):
    """Note what is known about a car and what is missing. A car has one open note per topic: a second
    one replaces its text (and its ad link, when one is given). Returns an error message or None."""
    note = (note or "").strip()
    if topic not in NOTE_TOPICS:
        return f"Nieznany temat: {topic} (dozwolone: {', '.join(NOTE_TOPICS)})."
    if not note:
        return "Opisz, co wiadomo i czego brakuje."
    if not conn.execute("SELECT 1 FROM vehicles WHERE vin = ?", (vin,)).fetchone():
        return f"Nie ma auta z VIN-em {vin}."
    conn.execute("""
        INSERT INTO review_notes (vin, topic, note, ad_url) VALUES (?, ?, ?, ?)
        ON CONFLICT (vin, topic) WHERE resolved_at IS NULL
        DO UPDATE SET note = excluded.note, ad_url = COALESCE(excluded.ad_url, ad_url), updated_at = datetime('now')
    """, (vin, topic, note, (ad_url or "").strip() or None))
    conn.commit()
    return None


def review_notes(conn, resolved=False, limit=200, vin=None):
    """Open notes, oldest first (or the latest resolved ones), each with its car (one query). With
    `vin`, only that car's notes (the car's page)."""
    order = "n.resolved_at DESC" if resolved else "n.created_at, n.id"
    return [dict(r) for r in conn.execute(f"""
        SELECT n.id, n.vin, n.topic, n.note, n.ad_url, n.created_at, n.updated_at, n.resolved_at,
               v.car_id, v.make, v.model, v.variant, v.year, v.registration_plate
        FROM review_notes n JOIN vehicles v ON v.vin = n.vin
        WHERE n.resolved_at IS {'NOT ' if resolved else ''}NULL {"AND n.vin = ?" if vin else ""}
        ORDER BY {order}
        LIMIT ?
    """, ((vin,) if vin else ()) + (limit,)).fetchall()]


def open_note_count(conn):
    return conn.execute("SELECT COUNT(*) FROM review_notes WHERE resolved_at IS NULL").fetchone()[0]


def set_note_resolved(conn, note_id, resolved):
    """Tick a note off (or open it again). Returns an error message, or None when done."""
    try:
        cur = conn.execute("UPDATE review_notes SET resolved_at = CASE WHEN ? THEN datetime('now') END WHERE id = ?",
                           (1 if resolved else 0, note_id))
    except Exception as exc:   # the unique index of open notes (sqlite3.IntegrityError, or D1's error)
        if "UNIQUE" not in str(exc).upper():
            raise
        return "To auto ma już otwartą notatkę w tym temacie."
    conn.commit()
    return None if cur.rowcount else "Nie ma takiej notatki."


# ── Weryfikacja (/verify): every car with something left to check, one row per car ──

NORTH_AMERICA = "('USA', 'USA/Kanada', 'Kanada')"

# What can be left to check on a car: its label and the SQL listing the VINs it applies to. Each
# reads through an index, except "damage" and "unchecked", which read the vehicles table (a few
# thousand rows).
VERIFY_ISSUES = {
    "plate": ("Tablica", "SELECT vin FROM plate_review_queue WHERE status = 'pending'"),
    "cepik": ("CEPiK nie zna", """SELECT l.vin FROM cepik_sync_log l JOIN vehicles cv ON cv.vin = l.vin
                                  WHERE l.status = 'not_found' AND cv.data_checked_at IS NULL
                                    AND NOT EXISTS (SELECT 1 FROM cepik_reports r WHERE r.vin = l.vin)"""),
    "origin": ("Rynek", "SELECT vin FROM vehicles WHERE ai_conflict = 1"),
    "notes": ("Notatki", "SELECT vin FROM review_notes WHERE resolved_at IS NULL"),
    "damage": ("Z Ameryki, bez szkody", f"""SELECT dv.vin FROM vehicles dv
                                            WHERE dv.origin_market IN {NORTH_AMERICA} AND dv.data_checked_at IS NULL
                                              AND NOT EXISTS (SELECT 1 FROM condition_reports cr
                                                              WHERE cr.vin = dv.vin AND cr.accident_free = 0)"""),
    "unchecked": ("Niesprawdzone", "SELECT vin FROM vehicles WHERE data_checked_at IS NULL"),
}
# "Do zrobienia" (the default) is what a review left open; the last two are wider lists to go through
VERIFY_OPEN = ("plate", "cepik", "origin", "notes")
VERIFY_PER_PAGE = 30


def _verify_set(issue):
    return " UNION ".join(VERIFY_ISSUES[i][1] for i in VERIFY_OPEN) if issue == "open" else VERIFY_ISSUES[issue][1]


def verify_counts(conn):
    """How many cars each issue of the Weryfikacja page has, and "open" (any of VERIFY_OPEN), in one query."""
    keys = ["open", *VERIFY_ISSUES]
    row = conn.execute("SELECT " + ", ".join(
        f"(SELECT COUNT(*) FROM vehicles c WHERE c.vin IN ({_verify_set(k)})) AS {k}" for k in keys)).fetchone()
    return {k: row[k] or 0 for k in keys}


def verify_search_sql(q):
    """The Weryfikacja search: a car ID (#123), else part of the VIN or of the plate. Returns the SQL
    condition on alias v and its parameters."""
    q = (q or "").strip().lstrip("#").strip().upper()
    if not q:
        return "", []
    if q.isdigit():
        return " AND v.car_id = ?", [int(q)]
    term = f"%{q.replace(' ', '')}%"
    return " AND (v.vin LIKE ? OR UPPER(REPLACE(COALESCE(v.registration_plate, ''), ' ', '')) LIKE ?)", [term, term]


def verify_cars(conn, issue="open", q="", page=1):
    """One page of the Weryfikacja list: the cars with the issue (newest car ID first), each with what is
    open on it (its plate card, CEPiK miss, origin conflict, notes, North American origin without a
    damage entry), and the total number of such cars. Notes come with their text."""
    from webapp.helpers import car_flags_sql
    cars_sql = _verify_set(issue)
    search, params = verify_search_sql(q)
    total = conn.execute(f"SELECT COUNT(*) FROM vehicles v WHERE v.vin IN ({cars_sql}){search}", params).fetchone()[0]
    cars = [dict(r) for r in conn.execute(f"""
        SELECT v.vin, v.make, v.model, v.variant, v.year, v.origin_market, v.ai_suggested_market, v.ai_reasoning,
               v.ai_conflict AS has_origin, {car_flags_sql("v")},
               (SELECT q.id FROM plate_review_queue q WHERE q.vin = v.vin AND q.status = 'pending' ORDER BY q.id DESC LIMIT 1) AS card_id,
               (SELECT q.crop_path FROM plate_review_queue q WHERE q.vin = v.vin AND q.status = 'pending' ORDER BY q.id DESC LIMIT 1) AS card_crop,
               (SELECT q.detected_plate FROM plate_review_queue q WHERE q.vin = v.vin AND q.status = 'pending' ORDER BY q.id DESC LIMIT 1) AS card_reading,
               (SELECT p.source_url FROM pending_listings p WHERE p.vin = v.vin AND COALESCE(p.source_url, '') <> ''
                ORDER BY p.id DESC LIMIT 1) AS ad_url,
               v.vin IN ({VERIFY_ISSUES["cepik"][1]}) AS has_cepik,
               v.vin IN ({VERIFY_ISSUES["damage"][1]}) AS has_damage
        FROM vehicles v
        WHERE v.vin IN ({cars_sql}){search}
        ORDER BY v.car_id DESC
        LIMIT ? OFFSET ?
    """, (*params, VERIFY_PER_PAGE, (max(page, 1) - 1) * VERIFY_PER_PAGE)).fetchall()]
    notes = {}
    if cars:
        marks = ", ".join("?" * len(cars))
        for n in conn.execute(f"""
            SELECT id, vin, topic, note, ad_url, created_at FROM review_notes
            WHERE resolved_at IS NULL AND vin IN ({marks}) ORDER BY created_at, id
        """, [c["vin"] for c in cars]):
            notes.setdefault(n["vin"], []).append(dict(n))
    for c in cars:
        c["notes"] = notes.get(c["vin"], [])
    return cars, total
