"""MCP server for checking, together with Claude, the data of the cars that entered the database:
plate, first registration date, origin market and damage. Cars not checked yet form a queue; a car is
shown with all its ads, photos, CEPiK report and damage marks, and marked "Dane sprawdzone" when done.
The /plates cards (with their photos and CEPiK lookups) and Bielik's origin conflicts have their own tools.

It runs locally over stdio (Claude Code picks it up from .mcp.json; Claude Desktop can run the same
command) on the database the scripts use: .env with DB_BACKEND=d1 is production. Decisions go through
the same functions as the screens (webapp/blueprints/plates.py, review.py, webapp/services/verification.py),
so a decision here is the same as one made on the screen. Every tool that writes is marked so, and the
client asks before it runs.

    pip install -r requirements-mcp.txt
    .venv/bin/python scripts/review_mcp.py
"""
import base64
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from mcp.server.mcpserver import Image, MCPServer
from mcp_types import ToolAnnotations
from PIL import Image as PILImage

import db
from validation import MARKETS, is_valid_first_registration_date
from webapp.blueprints.plates import plate_cards, review_card
from webapp.blueprints.review import ORIGIN_UNKNOWN, decide_origin, origin_conflicts
from webapp.services import verification
from webapp.services.plate_rules import plate_kind
from webapp.services.plates import normalize_plate

MAX_PHOTOS = 10
PHOTO_SIDE = 1280          # px, longer side: enough to read a plate, small enough for the model
DESCRIPTION_CHARS = 4000
MAX_ADS = 5                # a car's ads shown in full by show_car, newest first

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

server = MCPServer(
    name="sportscar-review",
    instructions=(
        "Tools for checking the data of cars in SportsCar DB: plate, first registration date, origin market "
        "and damage. Car by car: list_cars_to_check, show_car (all its ads with descriptions and photos, the "
        "CEPiK report with its events, damage marks and history, Bielik's view of the origin). Fix what is "
        "wrong with the set_* / add_* tools, then mark_car_checked. The plate goes through its /plates card: "
        "list_plate_cards (only_needing_person first), show_plate_card (plate crop and photos: read the plate "
        "yourself), then check_plate_in_cepik with the exact first registration date (ads often give only "
        "the year; an import's date in Poland is not its first registration abroad, CEPiK events say "
        "'Pierwsza rejestracja za granicą'). A confirmed lookup approves the card by itself. Every other "
        "decision only when the user agrees; when unsure, leave the car unchecked and say why. Polish plates "
        "only: CEPiK does not know cars on foreign plates. Talk to the user in Polish."
    ),
)


def _db():
    return db.get_db()


def _ad(conn, card):
    """The card's listing: its own, else the newest one of its VIN."""
    return conn.execute("""
        SELECT raw_title, raw_description, source_url, price_pln, mileage_km, location_city, first_registration_date,
               registration_plate, seller_type
        FROM pending_listings
        WHERE id = COALESCE(?, (SELECT id FROM pending_listings WHERE vin = ? ORDER BY id DESC LIMIT 1))
    """, (card["listing_id"], card["vin"])).fetchone()


def _pending_card(conn, card_id):
    return next((c for c in plate_cards(conn, "pending") if c["id"] == card_id), None)


def _summary(card):
    return {
        "card_id": card["id"], "vin": card["vin"],
        "car": " ".join(str(x) for x in (card["make"], card["model"], card["variant"], card["year"]) if x),
        "photo_reading": card["reading"], "suggested_plate": card["suggested_plate"],
        "plate_in_ad": normalize_plate(card["car_plate"]) or None,
        "first_registration_dates": card["dates"], "cepik_lookups_left": card["checks_left"],
        "hints": card["hints"],
    }


def _image(data: bytes) -> Image:
    """The picture as a JPEG no longer than PHOTO_SIDE on either side."""
    img = PILImage.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((PHOTO_SIDE, PHOTO_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82)
    return Image(data=out.getvalue(), format="jpeg")


def _fetch_photo(url: str):
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return _image(resp.content)
    except Exception as e:  # a photo gone from the portal must not lose the rest of the card
        return f"(zdjęcie niedostępne: {url[:80]}… {type(e).__name__})"


@server.tool(annotations=READ)
def list_plate_cards(limit: int = 20, offset: int = 0, only_needing_person: bool = False) -> str:
    """Pending /plates cards: car, the plate read from the photo and what the Polish plate rules make of
    it, the plate the ad gives, the first registration dates known, the automatic CEPiK lookups still
    queued, and hints why CEPiK may not know the car. only_needing_person: just the cards the automatic
    CEPiK lookups are done with (those queued are checked by the nightly job anyway)."""
    conn = _db()
    try:
        cards = plate_cards(conn, "pending")
    finally:
        conn.close()
    needing = [c for c in cards if c["checks_left"] == 0]
    shown = needing if only_needing_person else cards
    return json.dumps({
        "pending": len(cards), "needing_person": len(needing), "shown_from": offset,
        "cards": [_summary(c) for c in shown[offset:offset + max(1, min(limit, 100))]],
    }, ensure_ascii=False, indent=1)


@server.tool(annotations=READ, structured_output=False)
def show_plate_card(card_id: int, photos: int = 4) -> list:
    """One pending card in full: the ad (title, description, link, price, city, dates), the CEPiK pairs
    already asked, the plate crop the photo reading came from, and up to `photos` ad photos (max 10),
    the one the plate was found on first."""
    conn = _db()
    try:
        card = _pending_card(conn, card_id)
        ad = _ad(conn, card) if card else None
    finally:
        conn.close()
    if not card:
        return [f"Karta {card_id} nie czeka na weryfikację (zatwierdzona, odrzucona albo nie istnieje)."]
    info = {**_summary(card), "cepik_asked": [{"plate": p, "date": d} for p, d in card["cepik_asked"]]}
    if ad:
        description = ad["raw_description"] or ""
        info["ad"] = {
            "title": ad["raw_title"], "url": ad["source_url"], "price_pln": ad["price_pln"],
            "mileage_km": ad["mileage_km"], "city": ad["location_city"], "seller_type": ad["seller_type"],
            "first_registration_date": ad["first_registration_date"],
            "description": description[:DESCRIPTION_CHARS] + ("…" if len(description) > DESCRIPTION_CHARS else ""),
        }
    content = [json.dumps(info, ensure_ascii=False, indent=1)]
    crop = card["crop_path"] or ""
    if crop.startswith("data:image"):
        content += ["Wycinek tablicy, z którego pochodzi odczyt:", _image(base64.b64decode(crop.split(",", 1)[1]))]
    urls = [card["photo_url"]] if card["photo_url"] else []
    urls += [u for u in card["photos"] if isinstance(u, str) and u not in urls]
    for i, url in enumerate(urls[:max(0, min(photos, MAX_PHOTOS))], 1):
        content += [f"Zdjęcie {i}{' (na nim znaleziono tablicę)' if url == card['photo_url'] else ''}:", _fetch_photo(url)]
    return content


_cepik = None


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True))
def check_plate_in_cepik(card_id: int, plate: str, first_registration_date: str) -> str:
    """Ask CEPiK (the state vehicle register) about a pending card's car with this plate and first
    registration date (YYYY-MM-DD, exact day). When CEPiK knows this same car, the card is approved with
    the plate, the report is saved and the car takes that date. A miss is remembered, so the same pair
    is not asked again; it means the plate, the date or both are wrong (or the car is not registered in
    Poland)."""
    global _cepik
    from scripts.fetch_cepik import CepikClient, record_plate_check

    plate = normalize_plate(plate)
    if not plate_kind(plate):
        return f"{plate} nie jest polską tablicą: CEPiK zna tylko auta zarejestrowane w Polsce."
    if not is_valid_first_registration_date(first_registration_date):
        return "Niepoprawna data: RRRR-MM-DD, od 1980, nie z przyszłości."
    conn = _db()
    try:
        card = conn.execute("SELECT id, vin, status FROM plate_review_queue WHERE id = ?", (card_id,)).fetchone()
        if not card or card["status"] != "pending":
            return f"Karta {card_id} nie czeka na weryfikację."
        if conn.execute("SELECT 1 FROM cepik_plate_checks WHERE vin = ? AND plate = ? AND first_registration_date = ?",
                        (card["vin"], plate, first_registration_date)).fetchone():
            return f"{plate} z datą {first_registration_date} było już sprawdzane dla tego auta: CEPiK go nie znalazł."
        _cepik = _cepik or CepikClient()
        report = _cepik.fetch_vehicle_data(card["vin"], plate, first_registration_date)
        outcome = record_plate_check(conn, {"card_id": card_id, "vin": card["vin"], "plate": plate,
                                            "first_registration_date": first_registration_date},
                                     report, _cepik.last_status)
    finally:
        conn.close()
    if outcome == "confirmed":
        return json.dumps({"outcome": "Potwierdzone przez CEPiK: karta zatwierdzona, raport zapisany.",
                           "report": {k: report.get(k) for k in (
                               "make", "model", "year_of_manufacture", "first_registration_date", "registration_status",
                               "total_owners", "last_odometer_km", "last_odometer_date", "is_stolen")}},
                          ensure_ascii=False, indent=1)
    return {
        "not_found": "CEPiK nie zna auta z tą tablicą i datą (zapamiętane, nie będzie pytane ponownie).",
        "other_car": "CEPiK zwrócił inne auto niż to (zapamiętane, bez zatwierdzenia).",
        "error": "CEPiK nie odpowiedział (przerwa albo limit). Spróbuj później.",
        "gone": f"Karta {card_id} została w międzyczasie rozpatrzona.",
    }[outcome]


def _review(card_id: int, action: str, plate=None) -> str:
    conn = _db()
    try:
        payload, _status = review_card(conn, card_id, action, plate)
    finally:
        conn.close()
    return json.dumps(payload, ensure_ascii=False)


@server.tool(annotations=WRITE)
def approve_plate(card_id: int, plate: str) -> str:
    """Approve a /plates card with this plate, without CEPiK: the car keeps it. Prefer
    check_plate_in_cepik; use this only when the user agrees (e.g. the plate is clearly visible but the
    first registration date is unknown)."""
    return _review(card_id, "approve", plate)


@server.tool(annotations=WRITE)
def reject_plate(card_id: int) -> str:
    """Reject a /plates card: the plate is missing, unreadable or foreign, and the car loses the plate it
    had. Only when the user agrees."""
    return _review(card_id, "reject")


@server.tool(annotations=WRITE)
def undo_plate_review(card_id: int) -> str:
    """Put an approved or rejected /plates card back to pending, undoing what the review did to the car."""
    return _review(card_id, "revert")


@server.tool(annotations=READ)
def list_origin_conflicts(limit: int = 20) -> str:
    """Cars where Bielik (the AI that read the ads) and the stored origin market disagree, with his
    reasoning and the links to the car's live ads."""
    conn = _db()
    try:
        cars, ads = origin_conflicts(conn)
    finally:
        conn.close()
    return json.dumps({
        "conflicts": len(cars), "markets": MARKETS + [ORIGIN_UNKNOWN],
        "cars": [{**{k: c[k] for k in ("vin", "make", "model", "variant", "year", "origin_market",
                                       "ai_suggested_market", "ai_reasoning")},
                  "ads": [a["source_url"] for a in ads.get(c["vin"], [])]} for c in cars[:max(1, min(limit, 100))]],
    }, ensure_ascii=False, indent=1)


@server.tool(annotations=WRITE)
def set_origin_market(vin: str, market: str) -> str:
    """Decide a car's origin market, flagged by Bielik or not: "Polska", "Europa", "USA", "Kanada",
    "Japonia", "Szwajcaria", "Zatoka Perska", or "nieznany". Kept from then on: scraping does not
    overwrite it and Bielik does not flag it again. Only when the user agrees."""
    conn = _db()
    try:
        error, _status = decide_origin(conn, vin, market)
    finally:
        conn.close()
    return error or f"Zapisano rynek: {market}."


# ── Checking a car's data ─────────────────────────────────────────────────────

def _car_name(car):
    return " ".join(str(x) for x in (car["make"], car["model"], car["variant"], car["year"]) if x)


def _photo_urls(photos_json):
    try:
        photos = json.loads(photos_json or "[]")
    except ValueError:
        return []
    return [u for u in photos if isinstance(u, str)] if isinstance(photos, list) else []


def _by_vin(conn, sql, vins):
    """Rows of `sql` (with {vins} for the placeholders) for these cars, grouped by VIN."""
    rows = {}
    for r in conn.execute(sql.format(vins=",".join("?" * len(vins))), vins):
        rows.setdefault(r["vin"], []).append(r)
    return rows


@server.tool(annotations=READ)
def list_cars_to_check(limit: int = 10, offset: int = 0) -> str:
    """Cars with an approved ad whose data (plate, first registration date, origin, damage) nobody has
    checked yet, newest first, each with what stands out: no plate or a pending /plates card, no date
    or only a year, no origin or Bielik disagreeing, damage marks and damage history."""
    conn = _db()
    try:
        cars, total = verification.cars_to_check(conn, max(1, min(limit, 50)), max(0, offset))
        vins = [c["vin"] for c in cars]
        marks = cards = history = {}
        if vins:
            marks = _by_vin(conn, """
                SELECT DISTINCT o.vin, d.source, d.source_listing_id, d.reason, d.dismissed
                FROM damaged_listings d JOIN listing_observations o
                  ON o.source = d.source AND o.source_listing_id = d.source_listing_id
                WHERE o.vin IN ({vins})""", vins)
            cards = _by_vin(conn, "SELECT vin, id FROM plate_review_queue WHERE status = 'pending' AND vin IN ({vins})", vins)
            history = _by_vin(conn, "SELECT vin FROM condition_reports WHERE accident_free = 0 AND vin IN ({vins})", vins)
    finally:
        conn.close()
    out = []
    for c in cars:
        vin, date, notes = c["vin"], c["first_registration_date"], []
        if vin in cards:
            notes.append(f"tablica czeka na weryfikację (karta {cards[vin][0]['id']})")
        elif not c["registration_plate"]:
            notes.append("brak tablicy")
        if not date:
            notes.append("brak daty pierwszej rejestracji")
        elif date.endswith("-01-01"):
            notes.append(f"data {date} to pewnie sam rok")
        if not c["origin_market"]:
            notes.append("brak rynku")
        if c["ai_conflict"]:
            notes.append(f"Bielik uważa, że rynek to {c['ai_suggested_market']}")
        active = [m["reason"] or "portal" for m in marks.get(vin, []) if not m["dismissed"]]
        if active:
            notes.append("oznaczone jako uszkodzone: " + "; ".join(active))
        if vin in history:
            notes.append(f"wpisy o szkodach w historii: {len(history[vin])}")
        out.append({"vin": vin, "car": _car_name(c), "plate": c["registration_plate"], "first_registration_date": date,
                    "origin_market": c["origin_market"], "added": c["created_at"], "to_look_at": notes})
    return json.dumps({"not_checked": total, "shown_from": offset, "cars": out}, ensure_ascii=False, indent=1)


@server.tool(annotations=READ, structured_output=False)
def show_car(vin: str, photos: int = 4) -> list:
    """Everything needed to check one car's plate, first registration date, origin and damage: the car's
    stored data, its /plates cards, the CEPiK report with its events (e.g. "Pierwsza rejestracja za
    granicą"), Bielik's view of the origin, damage marks (the portal's or a quote from the ad) and damage
    history, its live ads (up to 5, newest first, with descriptions), and up to `photos` photos (max 10)."""
    conn = _db()
    try:
        car = conn.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,)).fetchone()
        if not car:
            return [f"Nie ma auta z VIN-em {vin}."]
        ads = conn.execute("""
            SELECT source, source_url, status, scraped_at, raw_title, raw_description, photos, price_pln, mileage_km,
                   location_city, seller_type, registration_plate, first_registration_date
            FROM pending_listings WHERE vin = ? AND status IN ('approved', 'pending') ORDER BY id DESC
        """, (vin,)).fetchall()
        marks = verification.damage_marks(conn, vin)
        history = conn.execute("""SELECT report_date, country, inspection_by, notes FROM condition_reports
                                  WHERE vin = ? AND accident_free = 0 ORDER BY report_date DESC""", (vin,)).fetchall()
        cepik = conn.execute("SELECT * FROM cepik_reports WHERE vin = ?", (vin,)).fetchone()
        cards = conn.execute("SELECT id, status, detected_plate, reviewed_plate FROM plate_review_queue WHERE vin = ? "
                             "ORDER BY id DESC", (vin,)).fetchall()
    finally:
        conn.close()
    car = dict(car)
    info = {
        "vin": vin, "car": _car_name(car), "data_checked_at": car.get("data_checked_at"),
        "plate": {"stored": car["registration_plate"],
                  "cards": [{"card_id": c["id"], "status": c["status"], "photo_reading": c["detected_plate"],
                             "reviewed_plate": c["reviewed_plate"]} for c in cards]},
        "first_registration_date": {"stored": car["first_registration_date"],
                                    "in_ads": sorted({a["first_registration_date"] for a in ads if a["first_registration_date"]})},
        "origin": {"stored": car["origin_market"], "decided_by_hand_at": car.get("origin_checked_at"),
                   "bielik": car.get("ai_suggested_market"), "bielik_disagrees": bool(car.get("ai_conflict")),
                   "bielik_reasoning": car.get("ai_reasoning")},
        "damage": {"marks": [{"source": m["source"], "reason": m["reason"] or "portal", "dismissed": bool(m["dismissed"])}
                             for m in marks],
                   "history": [dict(h) for h in history]},
        "cepik": None,
        "ads": [],
    }
    if cepik:
        try:
            events = [{"date": e.get("date"), "event": e.get("name")} for e in json.loads(cepik["events_json"] or "[]")]
        except ValueError:
            events = []
        info["cepik"] = {**{k: cepik[k] for k in ("registration_plate", "first_registration_date", "make", "model",
                                                  "registration_status", "total_owners", "last_odometer_km",
                                                  "last_odometer_date", "is_stolen", "fetched_at")},
                         "events": events}
    for a in ads[:MAX_ADS]:
        description = a["raw_description"] or ""
        info["ads"].append({
            "source": a["source"], "url": a["source_url"], "status": a["status"], "scraped_at": a["scraped_at"],
            "title": a["raw_title"], "price_pln": a["price_pln"], "mileage_km": a["mileage_km"],
            "city": a["location_city"], "seller_type": a["seller_type"], "plate": a["registration_plate"],
            "first_registration_date": a["first_registration_date"],
            "description": description[:DESCRIPTION_CHARS] + ("…" if len(description) > DESCRIPTION_CHARS else ""),
        })
    content = [json.dumps(info, ensure_ascii=False, indent=1)]
    urls = []
    for a in ads:   # the newest ad's photos first, then the older ads'
        urls += [u for u in _photo_urls(a["photos"]) if u not in urls]
    for i, url in enumerate(urls[:max(0, min(photos, MAX_PHOTOS))], 1):
        content += [f"Zdjęcie {i}:", _fetch_photo(url)]
    return content


@server.tool(annotations=WRITE)
def set_first_registration_date(vin: str, date: str) -> str:
    """Store a car's first registration date (YYYY-MM-DD, the exact day; for an import, the first
    registration abroad). The nightly CEPiK checks of its /plates card try it first. Prefer
    check_plate_in_cepik when the car has a pending card: it confirms plate and date together."""
    conn = _db()
    try:
        error = verification.set_first_registration_date(conn, vin, date)
    finally:
        conn.close()
    return error or f"Zapisano datę pierwszej rejestracji: {date}."


@server.tool(annotations=WRITE)
def set_damage_mark(vin: str, damaged: bool) -> str:
    """Confirm or dismiss the "Uszkodzony" mark the car's ads got (from the portal or a quote of their
    text). damaged=false: not damaged after all (a wrong match, a seller's mistake); the car's price
    goes back into the statistics. damaged=true brings dismissed marks back. Only when the user agrees."""
    conn = _db()
    try:
        if not conn.execute("SELECT 1 FROM vehicles WHERE vin = ?", (vin,)).fetchone():
            return f"Nie ma auta z VIN-em {vin}."
        if not verification.damage_marks(conn, vin):
            return ("Ogłoszenia tego auta nie mają oznaczenia „Uszkodzony”. Szkodę znalezioną w historii auta "
                    "dodaj przez add_damage_history.")
        verification.set_damage_dismissed(conn, vin, not damaged)
    finally:
        conn.close()
    return "Oznaczenie „Uszkodzony” przywrócone." if damaged else "Oznaczenie „Uszkodzony” zdjęte: auto wraca do statystyk cen."


@server.tool(annotations=WRITE)
def add_damage_history(vin: str, notes: str, country: str = "", report_date: str = "", source: str = "") -> str:
    """Add a damage found in the car's history (an ad saying it was damaged or repaired, a VIN check, an
    auction record): what was damaged, where (country), when (YYYY-MM-DD, default today) and where the
    information comes from (e.g. the ad's link). Shown on the car's page under its history. Only when the
    user agrees."""
    notes = " ".join(notes.split())
    if not notes:
        return "Opisz szkodę (co było uszkodzone)."
    if report_date and not is_valid_first_registration_date(report_date):
        return "Niepoprawna data: RRRR-MM-DD."
    conn = _db()
    try:
        if not conn.execute("SELECT 1 FROM vehicles WHERE vin = ?", (vin,)).fetchone():
            return f"Nie ma auta z VIN-em {vin}."
        verification.add_condition_report(conn, vin, report_date=report_date or None, accident_free=0, notes=notes,
                                          country=country.strip() or None, inspection_by=source.strip() or None)
    finally:
        conn.close()
    return "Dodano wpis o szkodzie do historii auta."


@server.tool(annotations=WRITE)
def mark_car_checked(vin: str, checked: bool = True) -> str:
    """Mark the car's data (plate, first registration date, origin, damage) as checked ("Dane sprawdzone"
    on its page); it leaves the list_cars_to_check queue. checked=false takes the mark back. Refused while
    the car's plate card is still pending on /plates."""
    conn = _db()
    try:
        if checked and conn.execute("SELECT 1 FROM plate_review_queue WHERE vin = ? AND status = 'pending'",
                                    (vin,)).fetchone():
            return "Tablica tego auta czeka jeszcze na /plates: najpierw ją zatwierdź albo odrzuć."
        found = verification.set_data_checked(conn, vin, checked)
    finally:
        conn.close()
    if not found:
        return f"Nie ma auta z VIN-em {vin}."
    return "Oznaczono: dane sprawdzone." if checked else "Cofnięto oznaczenie „Dane sprawdzone”."


if __name__ == "__main__":
    server.run()
