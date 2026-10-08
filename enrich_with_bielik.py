import os
import re
import json
import time
import requests
from datetime import datetime
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

def analyze_with_bielik(title: str, description: str, make: str, model: str, city: str = "") -> dict:
    clean_desc = clean_html(description)
    # Truncate if extremely long to keep prompt efficient
    if len(clean_desc) > 3500:
        clean_desc = clean_desc[:3500] + "..."

    prompt = f"""Jesteś rzeczoznawcą i ekspertem motoryzacyjnym. Przeanalizuj poniższe ogłoszenie samochodu {make} {model} i zwróć TYLKO czysty obiekt JSON (bez znaczników markdown, bez zbędnego tekstu):
{{
  "origin_market": "Europa" | "Polska" | "USA" | "Kanada" | "Japonia" | "Szwajcaria" | null,
  "origin_reasoning": "krótkie uzasadnienie pochodzenia (zwróć szczególną uwagę na zaprzeczenia np. 'NIE z USA')",
  "has_panoramic_roof": true | false,
  "interior_color": "np. czarny, brązowy, czerwony, beżowy lub null",
  "interior_material": "np. skóra, alcantara, materiał lub null",
  "key_equipment": ["3-5 najważniejszych cech wyposażenia"],
  "accident_status": "bezwypadkowy" | "uszkodzony" | "po kolizji" | null,
  "location_region": "jedno z 16 polskich województw: dolnośląskie | kujawsko-pomorskie | lubelskie | lubuskie | łódzkie | małopolskie | mazowieckie | opolskie | podkarpackie | podlaskie | pomorskie | śląskie | świętokrzyskie | warmińsko-mazurskie | wielkopolskie | zachodniopomorskie | null",
  "summary": "zwięzłe podsumowanie stanu, historii i wyposażenia w 2 zdaniach"
}}

Tytuł: {title}
Miasto/Lokalizacja: {city or 'Brak'}
Opis:
{clean_desc}"""

    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 1000
            }
        },
        timeout=120
    )
    resp.raise_for_status()
    raw_response = resp.json().get("response", "{}")
    return json.loads(raw_response)

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
        existing_region = r["location_region"]
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

            # Województwo (kod ISO np. 'PL-MZ')
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
            norm_db = normalize_market(db_market)
            norm_ai = normalize_market(ai_market)
            has_conflict = 0
            if norm_db and norm_ai and norm_db != norm_ai:
                # If DB is Polska and AI is Europa, not really a conflict
                if not (norm_db == "polska" and norm_ai == "europa"):
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
