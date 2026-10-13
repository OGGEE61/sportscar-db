from db import make_placeholder_vin
from webapp.helpers import is_valid_registration_plate, safe_float, safe_int
from webapp.regions import CITY_TO_REGION
def infer_vehicle_specs(make, model, variant="", raw_title=""):
    """Infer known model specs for performance cars if fields are empty."""
    text = f"{make or ''} {model or ''} {variant or ''} {raw_title or ''}".lower()
    specs = {}

    if "rs4" in text:
        if "b9" in text or any(y in text for y in ["2017", "2018", "2019", "2020"]):
            specs = {"engine_cc": 2894, "engine_cyl": 6, "power_hp": 450, "body_type": "Kombi", "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}
        else: # B8 / B8.5
            specs = {"engine_cc": 4163, "engine_cyl": 8, "power_hp": 450, "body_type": "Kombi", "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "c63" in text or ("c 63" in text and ("w204" in text or "amg" in text or "mercedes" in text)):
        bt = "Kombi" if any(k in text for k in ["kombi", "t-modell", "estate", "wagon"]) else ("Coupe" if "coupe" in text else "Sedan")
        specs = {"engine_cc": 6208, "engine_cyl": 8, "power_hp": 457, "body_type": bt, "drivetrain": "RWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "e55" in text or ("e 55" in text and ("w211" in text or "amg" in text or "mercedes" in text)):
        bt = "Kombi" if any(k in text for k in ["kombi", "t-modell", "estate", "wagon"]) else "Sedan"
        specs = {"engine_cc": 5439, "engine_cyl": 8, "power_hp": 476, "body_type": bt, "drivetrain": "RWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "m4" in text:
        bt = "Kabriolet" if any(k in text for k in ["cabrio", "kabriolet", "convertible"]) else "Coupe"
        tm = "manual" if ("manual" in text or "manualna" in text) else "automatic"
        specs = {"engine_cc": 2979, "engine_cyl": 6, "power_hp": 431, "body_type": bt, "drivetrain": "RWD", "transmission": tm, "fuel_type": "petrol"}
    elif "m3" in text:
        tm = "manual" if ("manual" in text or "manualna" in text) else "automatic"
        specs = {"engine_cc": 2979, "engine_cyl": 6, "power_hp": 431, "body_type": "Sedan", "drivetrain": "RWD", "transmission": tm, "fuel_type": "petrol"}
    elif "rs3" in text:
        bt = "Sedan" if ("limousine" in text or "sedan" in text) else "Hatchback"
        specs = {"engine_cc": 2480, "engine_cyl": 5, "power_hp": 400, "body_type": bt, "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "x3 m" in text or "x3m" in text:
        specs = {"engine_cc": 2993, "engine_cyl": 6, "power_hp": 510, "body_type": "SUV", "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}

    return specs


def backfill_vehicle_specs(conn):
    """Backfills missing body_type, engine_cc, engine_cyl, drivetrain for existing vehicles."""
    try:
        rows = conn.execute("SELECT vin, make, model, variant, body_type, engine_cc, engine_cyl, power_hp, drivetrain, transmission FROM vehicles").fetchall()
        for r in rows:
            specs = infer_vehicle_specs(r["make"], r["model"], r["variant"])
            if not specs:
                continue
            updates = []
            vals = []
            for col in ["engine_cc", "engine_cyl", "body_type", "drivetrain", "power_hp", "transmission"]:
                val = r[col] if col in r.keys() else None
                if specs.get(col) and (val is None or val == "" or val == 0):
                    updates.append(f"{col} = ?")
                    vals.append(specs[col])
            if updates:
                vals.append(r["vin"])
                conn.execute(f"UPDATE vehicles SET {', '.join(updates)}, updated_at = datetime('now') WHERE vin = ?", vals)
        conn.commit()
    except Exception as e:
        print(f"Backfill error: {e}")


import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import json

def _enrich_location_with_nominatim(city_name):
    if not city_name: return None
    try:
        url = f"https://nominatim.openstreetmap.org/search?city={urllib.parse.quote(city_name)}&country=Poland&format=json&addressdetails=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'SportsCarDB/1.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data:
                state = data[0].get('address', {}).get('state', '').lower()
                mapping = {
                    "dolnośląskie": "PL-DS", "kujawsko-pomorskie": "PL-KP",
                    "lubelskie": "PL-LU", "lubuskie": "PL-LB", "łódzkie": "PL-LD",
                    "małopolskie": "PL-MA", "mazowieckie": "PL-MZ", "opolskie": "PL-OP",
                    "podkarpackie": "PL-PK", "podlaskie": "PL-PD", "pomorskie": "PL-PM",
                    "śląskie": "PL-SL", "świętokrzyskie": "PL-SK",
                    "warmińsko-mazurskie": "PL-WN", "wielkopolskie": "PL-WP",
                    "zachodniopomorskie": "PL-ZP"
                }
                for k, v in mapping.items():
                    if k in state: return v
    except Exception as e:
        print(f"Nominatim error for {city_name}:", e)
    return None

def _enrich_otomoto_ad(url):
    try:
        if not url or "otomoto.pl" not in url: return {}
        from curl_cffi import requests
        r = requests.get(url, impersonate="chrome", timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        reg_plate, reg_date = None, None
        for el in soup.find_all(["p", "span", "div"]):
            txt = el.get_text(strip=True)
            if txt == "Numer rejestracyjny pojazdu":
                nxt = el.find_next_sibling()
                if nxt:
                    candidate = nxt.get_text(strip=True)
                    if is_valid_registration_plate(candidate):
                        reg_plate = candidate.upper()
            elif txt == "Pierwsza rejestracja":
                nxt = el.find_next_sibling()
                if nxt: reg_date = nxt.get_text(strip=True)
        return {"registration_plate": reg_plate, "first_registration_date": reg_date}
    except Exception as e:
        print("Enrich error:", e)
    return {}

def _approve_listing(conn, listing, overrides=None):
    """Upsert vehicle + insert observation + mark pending row approved.

    overrides: dict of form fields that take precedence over listing values
               (used by the manual review form). Pass None for auto-approve.
    Returns the VIN string used.
    """
    overrides = overrides or {}
    listing = dict(listing)

    # Scrape ad details dynamically if missing
    enriched = {}
    if not overrides:
        enriched = _enrich_otomoto_ad(listing.get("source_url"))

    vin = (overrides.get("vin") or listing["vin"] or "").strip().upper()
    if not vin or len(vin) != 17:
        vin = make_placeholder_vin(
            listing["source"] or "olx",
            listing["source_listing_id"] or str(listing["id"])
        )

    def _get(key, cast=None):
        val = overrides.get(key)
        if not val and key in listing.keys():
            val = listing[key]
        if not val and key in enriched:
            val = enriched[key]
        if val is None or val == "":
            return None
        return cast(val) if cast else val

    raw_title = listing["raw_title"] if "raw_title" in listing.keys() else ""
    inferred = infer_vehicle_specs(
        _get("make"), _get("model"), _get("variant"), raw_title
    )
    final_body_type    = _get("body_type") or inferred.get("body_type")
    final_engine_cc    = _get("engine_cc", safe_int) or inferred.get("engine_cc")
    final_engine_cyl   = _get("engine_cyl", safe_int) or inferred.get("engine_cyl")
    final_power_hp     = _get("power_hp", safe_int) or inferred.get("power_hp")
    final_drivetrain   = _get("drivetrain") or inferred.get("drivetrain")
    final_transmission = _get("transmission") or inferred.get("transmission")
    
    # Store these in variables so we can inject them into the DB later
    final_reg_plate = _get("registration_plate")
    if final_reg_plate and not is_valid_registration_plate(final_reg_plate):
        final_reg_plate = None
    final_first_reg = _get("first_registration_date")

    # Enrich location with CITY_TO_REGION or Nominatim
    loc_city = _get("location_city")
    loc_region = listing.get("location_region")
    if not loc_region and loc_city:
        loc_region = CITY_TO_REGION.get(loc_city)
    if loc_city and (not loc_region or len(loc_region) != 5):
        best_region = _enrich_location_with_nominatim(loc_city)
        if best_region: loc_region = best_region

    if vin.startswith("UNVERIFIED"):
        initial_status = "placeholder"
    elif final_reg_plate:
        initial_status = "verified"
    else:
        initial_status = "unverified"

    conn.execute("""
        INSERT INTO vehicles
          (vin, make, model, variant, year, body_type,
           engine_cc, engine_cyl, power_hp, drivetrain, transmission,
           color_ext, color_int, equipment, registration_plate, first_registration_date, origin_market,
           vin_status, source_method)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vin) DO UPDATE SET
          make        = COALESCE(excluded.make, make),
          model       = COALESCE(excluded.model, model),
          variant     = COALESCE(excluded.variant, variant),
          power_hp    = COALESCE(excluded.power_hp, power_hp),
          engine_cc   = COALESCE(excluded.engine_cc, engine_cc),
          engine_cyl  = COALESCE(excluded.engine_cyl, engine_cyl),
          body_type   = COALESCE(excluded.body_type, body_type),
          drivetrain  = COALESCE(excluded.drivetrain, drivetrain),
          transmission= COALESCE(excluded.transmission, transmission),
          registration_plate = COALESCE(excluded.registration_plate, registration_plate),
          first_registration_date = COALESCE(excluded.first_registration_date, first_registration_date),
          origin_market = COALESCE(excluded.origin_market, origin_market),
          color_int   = COALESCE(excluded.color_int, color_int),
          equipment   = COALESCE(excluded.equipment, equipment),
          updated_at  = datetime('now')
    """, (
        vin,
        _get("make") or "Unknown",
        _get("model") or "Unknown",
        _get("variant"),
        safe_int(overrides.get("year"), listing.get("year") or 0),
        final_body_type,
        final_engine_cc,
        final_engine_cyl,
        final_power_hp,
        final_drivetrain,
        final_transmission,
        _get("color_ext"),
        _get("color_int"),
        _get("equipment"),
        final_reg_plate,
        final_first_reg,
        _get("origin_market"),
        initial_status,
        f"scraper-{listing['source']}",
    ))

    conn.execute("""
        INSERT INTO listing_observations
          (vin, source, source_listing_id, source_url, title,
           price_pln, mileage_km, location_city, location_region,
           seller_type, seller_name, registration_plate,
           first_seen_at, observed_at, source_method, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        vin, listing["source"],
        listing["source_listing_id"],
        listing["source_url"],
        listing["raw_title"],
        safe_float(overrides.get("price_pln"), listing.get("price_pln")),
        safe_int(overrides.get("mileage_km"), listing.get("mileage_km")),
        loc_city,
        loc_region,
        overrides.get("seller_type")   or listing["seller_type"] or "private",
        overrides.get("seller_name")   or listing["seller_name"],
        final_reg_plate,
        listing["scraped_at"], listing["scraped_at"],
        f"scraper-{listing['source']}",
        overrides.get("notes"),
    ))

    conn.execute("""
        UPDATE pending_listings
        SET status='approved', reviewed_at=datetime('now'), review_notes=?
        WHERE id=?
    """, (overrides.get("notes"), listing["id"]))

    local_photo = listing["local_photo"] if "local_photo" in listing.keys() else None
    if local_photo:
        conn.execute(
            "UPDATE vehicles SET photo=? WHERE vin=? AND (photo IS NULL OR photo='')",
            (local_photo, vin)
        )

    # Jeśli tablica pochodzi ze zdjęcia (plate_review_queue), dodaj tag 'photo extracted'
    try:
        lid_str = str(listing.get("id") or "")
        pq = conn.execute("SELECT id FROM plate_review_queue WHERE (vin=? OR listing_id=?) AND status='approved'", (vin, lid_str)).fetchone()
        if pq:
            conn.execute("DELETE FROM tags WHERE vin=? AND tag IN ('missing plates', 'Missing plates')", (vin,))
            conn.execute("INSERT OR IGNORE INTO tags (vin, tag, source_method) VALUES (?, 'photo extracted', 'photo-extracted')", (vin,))
    except Exception:
        pass

    return vin
