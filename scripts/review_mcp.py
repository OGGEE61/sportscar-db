"""MCP server for reviewing ads together with Claude: the /plates cards with their photos, CEPiK
lookups of a plate and date, and the cars where Bielik and the stored origin market disagree.

It runs locally over stdio (Claude Code picks it up from .mcp.json; Claude Desktop can run the same
command) on the database the scripts use: .env with DB_BACKEND=d1 is production. Decisions go through
the same functions as the screens (webapp/blueprints/plates.py, review.py), so approving here is the
same as approving on /plates. Every tool that writes is marked so, and the client asks before it runs.

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
from webapp.services.plate_rules import plate_kind
from webapp.services.plates import normalize_plate

MAX_PHOTOS = 10
PHOTO_SIDE = 1280          # px, longer side: enough to read a plate, small enough for the model
DESCRIPTION_CHARS = 4000

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

server = MCPServer(
    name="sportscar-review",
    instructions=(
        "Tools for reviewing car ads in SportsCar DB. Plates (/plates): every pending card is a car whose "
        "registration plate needs confirming. Workflow: list_plate_cards (start with only_needing_person), "
        "show_plate_card to see the plate crop, the ad photos and the description, read the plate yourself, "
        "find the exact first registration date (ads often give only the year; an import's date in Poland "
        "is not its first registration abroad), then check_plate_in_cepik. A confirmed lookup approves the "
        "card by itself. approve_plate without CEPiK, reject_plate and decide_origin only when the user "
        "agrees. Polish plates only: CEPiK does not know cars on foreign plates. The app's UI and messages "
        "are in Polish; talk to the user in Polish."
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
    """Decide a flagged car's origin market: one of the markets list_origin_conflicts gives (or
    "nieznany"). Kept from then on: scraping does not overwrite it and Bielik does not flag it again.
    Only when the user agrees."""
    conn = _db()
    try:
        error, _status = decide_origin(conn, vin, market)
    finally:
        conn.close()
    return error or f"Zapisano rynek: {market}."


if __name__ == "__main__":
    server.run()
