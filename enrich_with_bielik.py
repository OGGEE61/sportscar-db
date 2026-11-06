import os
import re
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

from db import get_db
from app import CITY_TO_REGION, REGION_NAME_TO_CODE

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.environ.get("BIELIK_MODEL", "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M")

def clean_html(text: str) -> str:
    if not text:
        return ""
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # Collapse multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

MARKETS = ["Polska", "Europa", "USA", "Kanada", "Japonia", "Szwajcaria", "Zatoka Perska"]
ACCIDENT_STATUSES = ["bezwypadkowy", "uszkodzony", "po kolizji"]
REGIONS = ["dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie", "małopolskie", "mazowieckie",
           "opolskie", "podkarpackie", "podlaskie", "pomorskie", "śląskie", "świętokrzyskie",
           "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie"]
EMPTY_VALUES = {"", "null", "none", "brak", "brak danych", "brak informacji", "nie podano", "nieznany", "nieznane", "n/a"}

_NULLABLE_TEXT = {"type": ["string", "null"]}
# Sent to Ollama as `format`. Reasoning comes before the market so the model states its evidence first.
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "origin_reasoning": {"type": "string"},
        "origin_market": {"type": ["string", "null"], "enum": MARKETS + [None]},
        "has_panoramic_roof": {"type": "boolean"},
        "interior_color": _NULLABLE_TEXT,
        "interior_material": _NULLABLE_TEXT,
        "key_equipment": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "accident_status": {"type": ["string", "null"], "enum": ACCIDENT_STATUSES + [None]},
        "location_region": {"type": ["string", "null"], "enum": REGIONS + [None]},
        "summary": {"type": "string"},
    },
    "required": ["origin_reasoning", "origin_market", "has_panoramic_roof", "interior_color", "interior_material",
                 "key_equipment", "accident_status", "location_region", "summary"],
}


def build_prompt(title: str, description: str, make: str, model: str, city: str = "") -> str:
    clean_desc = clean_html(description)
    # Truncate if extremely long to keep prompt efficient
    if len(clean_desc) > 3500:
        clean_desc = clean_desc[:3500] + "..."

    return f"""Jesteś rzeczoznawcą i ekspertem motoryzacyjnym. Przeanalizuj poniższe ogłoszenie samochodu {make} {model} i zwróć TYLKO czysty obiekt JSON (bez znaczników markdown, bez zbędnego tekstu):
{{
  "origin_reasoning": "krótki cytat lub fakt z ogłoszenia wskazujący rynek pochodzenia; 'brak informacji', gdy ogłoszenie o tym nie mówi",
  "origin_market": "Polska" | "Europa" | "USA" | "Kanada" | "Japonia" | "Szwajcaria" | "Zatoka Perska" | null,
  "has_panoramic_roof": true | false,
  "interior_color": "np. czarny, brązowy, czerwony, beżowy lub null",
  "interior_material": "np. skóra, alcantara, materiał lub null",
  "key_equipment": ["3-5 najważniejszych cech wyposażenia"],
  "accident_status": "bezwypadkowy" | "uszkodzony" | "po kolizji" | null,
  "location_region": "jedno z 16 polskich województw: {' | '.join(REGIONS)} | null",
  "summary": "zwięzłe podsumowanie stanu, historii i wyposażenia w 2 zdaniach"
}}

Zasady:
- Opieraj się wyłącznie na treści ogłoszenia, niczego nie zgaduj.
- origin_market: wskaż rynek tylko, gdy ogłoszenie wprost mówi o pochodzeniu auta (np. "polski salon", "sprowadzony z USA"). Brak informacji to null, a nie "Europa". Siedziba dealera, serwis w Polsce ani polska instrukcja nie wskazują rynku. Zaprzeczenie "nie z USA" nie oznacza Polski.
- Pochodzenie z konkretnego kraju europejskiego (np. Niemcy, Francja) to "Europa". Polski salon to "Polska". Kraje Zatoki Perskiej (np. ZEA) to "Zatoka Perska". Rynek spoza listy to null.
- accident_status: "bezwypadkowy" tylko, gdy ogłoszenie wprost tak mówi; samo to, że auto jest nowe, zadbane lub od dealera, to null. Szkoda nienaprawiona (np. auto z aukcji ubezpieczeniowej z opisem uszkodzenia) to "uszkodzony", szkoda już naprawiona to "po kolizji". Same ślady użytkowania to nie szkoda.
- Pola, o których ogłoszenie nie mówi, ustaw na null, a nie "nie podano" ani "brak".

Tytuł: {title}
Miasto/Lokalizacja: {city or 'Brak'}
Opis:
{clean_desc}"""


def clean_analysis(data: dict) -> dict:
    """Keep only values we accept, whatever the model returned; anything else becomes None."""
    def text(value):
        if not isinstance(value, str) or value.strip().lower() in EMPTY_VALUES:
            return None
        return value.strip()

    def choice(value, allowed):
        value = text(value)
        return next((a for a in allowed if value and a.lower() == value.lower()), None)

    equipment = data.get("key_equipment")
    return {
        **data,
        "origin_reasoning": text(data.get("origin_reasoning")),
        "origin_market": choice(data.get("origin_market"), MARKETS),
        "has_panoramic_roof": data.get("has_panoramic_roof") is True,
        "interior_color": text(data.get("interior_color")),
        "interior_material": text(data.get("interior_material")),
        "key_equipment": [e.strip() for e in equipment if text(e)][:5] if isinstance(equipment, list) else [],
        "accident_status": choice(data.get("accident_status"), ACCIDENT_STATUSES),
        "location_region": choice(data.get("location_region"), REGIONS),
        "summary": text(data.get("summary")),
    }


def analyze_with_bielik(title: str, description: str, make: str, model: str, city: str = "",
                        model_name: str = None) -> dict:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model_name or MODEL_NAME,
            "prompt": build_prompt(title, description, make, model, city),
            "stream": False,
            "format": ANALYSIS_SCHEMA,
            "options": {
                "temperature": 0.1,
                "num_predict": 1000
            }
        },
        timeout=120
    )
    resp.raise_for_status()
    raw_response = resp.json().get("response", "{}")
    return clean_analysis(json.loads(raw_response))

def normalize_market(m: str) -> str:
    if not m:
        return ""
    m = m.strip().lower()
    if "usa" in m or "stan" in m:
        return "usa"
    if "kanad" in m:
        return "kanada"
    if "japon" in m:
        return "japonia"
    if "szwajcar" in m:
        return "szwajcaria"
    if "polsk" in m:
        return "polska"
    if "europ" in m or "niemc" in m:
        return "europa"
    return m

def markets_conflict(db_market: str, ai_market: str) -> bool:
    """True when the stored and suggested markets really disagree (either side empty is no conflict)."""
    norm_db = normalize_market(db_market)
    norm_ai = normalize_market(ai_market)
    if not norm_db or not norm_ai or norm_db == norm_ai:
        return False
    # Poland is in Europe, and the resolver's USA/Kanada covers both
    if {norm_db, norm_ai} == {"polska", "europa"}:
        return False
    if (db_market or "").strip().lower() == "usa/kanada" and norm_ai in ("usa", "kanada"):
        return False
    return True

def main():
    print(f"=== Rozpoczynam enricher Bielik AI ({MODEL_NAME}) ===")
    db = get_db()

    # Get all listings needing processing
    rows = db.execute("""
        SELECT id, vin, raw_title, raw_description, origin_market, make, model, location_city, location_region, source, source_listing_id
        FROM pending_listings
        WHERE (ai_processed_at IS NULL OR ai_summary IS NULL)
          AND raw_description IS NOT NULL
          AND length(raw_description) > 30
          AND status != 'rejected'
        ORDER BY id ASC
    """).fetchall()

    total = len(rows)
    print(f"Znaleziono {total} ogłoszeń do przetworzenia.")

    processed = 0
    conflicts = 0

    for idx, r in enumerate(rows, 1):
        listing_id = r["id"]
        vin = r["vin"]
        title = r["raw_title"] or ""
        desc = r["raw_description"] or ""
        db_market = r["origin_market"]
        make = r["make"] or ""
        model = r["model"] or ""
        city = r["location_city"] or ""
        source = r["source"]
        source_listing_id = r["source_listing_id"]

        print(f"\n[{idx}/{total}] ID: {listing_id} | {make} {model} ({vin})")

        try:
            data = analyze_with_bielik(title, desc, make, model, city=city)
            
            ai_market = data.get("origin_market")
            ai_reasoning = data.get("origin_reasoning")
            ai_summary = data.get("summary")
            key_eq = data.get("key_equipment") or []
            if data.get("has_panoramic_roof"):
                if not any("dach" in str(x).lower() or "szyber" in str(x).lower() for x in key_eq):
                    key_eq.append("Dach panoramiczny/szyberdach")
            ai_equipment_json = json.dumps(key_eq, ensure_ascii=False)
            
            interior = []
            if data.get("interior_color"):
                interior.append(data.get("interior_color"))
            if data.get("interior_material"):
                interior.append(data.get("interior_material"))
            ai_interior_str = " / ".join(interior) if interior else None

            # Voivodeship (ISO code, e.g. 'PL-MZ')
            ai_region_raw = data.get("location_region")
            ai_region = None
            if ai_region_raw:
                norm_raw = str(ai_region_raw).strip().lower()
                ai_region = REGION_NAME_TO_CODE.get(norm_raw)
            if not ai_region and city:
                ai_region = CITY_TO_REGION.get(city)
            if ai_region:
                print(f"  ✓ Region: {ai_region}")

            # Detect conflict
            has_conflict = 0
            if markets_conflict(db_market, ai_market):
                has_conflict = 1
                conflicts += 1
                print(f"  ⚠️ KONFLIKT RYNKU: Baza='{db_market}' vs Bielik='{ai_market}' (Powód: {ai_reasoning})")

            # Update pending_listings
            db.execute("""
                UPDATE pending_listings
                SET ai_summary = ?,
                    ai_suggested_market = ?,
                    ai_conflict = ?,
                    ai_reasoning = ?,
                    ai_equipment = ?,
                    ai_interior_color = ?,
                    location_region = COALESCE(location_region, ?),
                    ai_processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                ai_summary,
                ai_market,
                has_conflict,
                ai_reasoning,
                ai_equipment_json,
                ai_interior_str,
                ai_region,
                listing_id
            ))

            # Update listing_observations if region was determined
            if ai_region and source and source_listing_id:
                try:
                    db.execute("""
                        UPDATE listing_observations
                        SET location_region = COALESCE(location_region, ?)
                        WHERE source = ? AND source_listing_id = ?
                    """, (ai_region, source, source_listing_id))
                except Exception:
                    pass

            # Update vehicle in vehicles table if no conflict
            if vin:
                if has_conflict == 0:
                    db.execute("""
                        UPDATE vehicles
                        SET ai_summary = ?,
                            color_int = COALESCE(color_int, ?)
                        WHERE vin = ?
                    """, (ai_summary, ai_interior_str, vin))
                else:
                    db.execute("""
                        UPDATE vehicles
                        SET ai_summary = ?
                        WHERE vin = ?
                    """, (ai_summary, vin))

            print(f"  ✓ Zapisano: Rynek: {ai_market or 'Brak'}, Konflikt: {'TAK' if has_conflict else 'NIE'}")
            if ai_interior_str:
                print(f"  ✓ Wnętrze: {ai_interior_str}")
            if ai_region:
                print(f"  ✓ Województwo: {ai_region}")
            print(f"  ✓ TL;DR: {ai_summary}")
            processed += 1

        except Exception as e:
            print(f"  ❌ Błąd przetwarzania ID {listing_id}: {e}")
            try:
                db.execute("UPDATE pending_listings SET ai_processed_at = CURRENT_TIMESTAMP WHERE id = ?", (listing_id,))
            except Exception:
                pass

        time.sleep(0.3)

    print(f"\n=== Zakończono! Przetworzono {processed}/{total} ogłoszeń. Wykrytych konfliktów: {conflicts} ===")

if __name__ == "__main__":
    main()
