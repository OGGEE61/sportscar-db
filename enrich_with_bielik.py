import os
import re
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

from db import get_db
from validation import MARKETS
from webapp.regions import CITY_TO_REGION, REGION_NAME_TO_CODE

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


def _clip(description: str, limit: int) -> str:
    text = clean_html(description)
    return text[:limit] + "..." if len(text) > limit else text


def _prompt(task: str, body: str, extra_rules: str = "") -> str:
    """The instructions and JSON shape, around one ad (build_prompt) or all ads of a car (build_car_prompt)."""
    return f"""Jesteś rzeczoznawcą i ekspertem motoryzacyjnym. {task} i zwróć TYLKO czysty obiekt JSON (bez znaczników markdown, bez zbędnego tekstu):
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
- Pola, o których ogłoszenie nie mówi, ustaw na null, a nie "nie podano" ani "brak".{extra_rules}

{body}"""


def build_prompt(title: str, description: str, make: str, model: str, city: str = "") -> str:
    return _prompt(f"Przeanalizuj poniższe ogłoszenie samochodu {make} {model}",
                   f"Tytuł: {title}\nMiasto/Lokalizacja: {city or 'Brak'}\nOpis:\n{_clip(description, 3500)}")


CAR_AD_CHARS, CAR_TOTAL_CHARS = 3000, 7000   # per ad, and for all ads of a car (newest first)


def distinct_ads(ads: list) -> list:
    """The car's ads whose text differs (a cross-post to another portal often repeats it word for word)."""
    seen, out = set(), []
    for ad in ads:
        text = clean_html(ad["raw_description"])
        if text and text not in seen:
            seen.add(text)
            out.append(ad)
    return out


def build_car_prompt(ads: list, make: str, model: str) -> str:
    """One prompt for every ad of a car (ads newest first, as distinct_ads returns them); a single ad
    gets exactly the per-ad prompt."""
    if len(ads) == 1:
        ad = ads[0]
        return build_prompt(ad["raw_title"] or "", ad["raw_description"], make, model, ad["location_city"] or "")
    blocks, left = [], CAR_TOTAL_CHARS
    for i, ad in enumerate(ads, 1):
        if left <= 200:
            break
        desc = _clip(ad["raw_description"], min(CAR_AD_CHARS, left))
        left -= len(desc)
        blocks.append(f"Ogłoszenie {i} ({ad['source']}, {str(ad['scraped_at'])[:10]}):\n"
                      f"Tytuł: {ad['raw_title'] or ''}\nMiasto/Lokalizacja: {ad['location_city'] or 'Brak'}\nOpis:\n{desc}")
    return _prompt(
        f"Przeanalizuj poniższe ogłoszenia jednego samochodu {make} {model} (ten sam VIN, różne portale lub terminy)",
        "\n\n".join(blocks),
        "\n- Wszystkie ogłoszenia dotyczą tego samego auta: połącz zawarte w nich informacje w jedną ocenę. "
        "Gdy ogłoszenia sobie przeczą (np. pochodzenie, przebieg, historia szkód), napisz o tym w podsumowaniu.")


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


def _ask(prompt: str, model_name: str = None) -> dict:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model_name or MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "format": ANALYSIS_SCHEMA,
            # num_ctx: room for a car's several ads (Ollama's default context is shorter)
            "options": {"temperature": 0.1, "num_predict": 1000, "num_ctx": 8192},
        },
        timeout=300
    )
    resp.raise_for_status()
    return clean_analysis(json.loads(resp.json().get("response", "{}")))


def analyze_with_bielik(title: str, description: str, make: str, model: str, city: str = "",
                        model_name: str = None) -> dict:
    return _ask(build_prompt(title, description, make, model, city), model_name)


def analyze_car(ads: list, make: str, model: str) -> dict:
    return _ask(build_car_prompt(ads, make, model))


def stored_fields(data: dict) -> dict:
    """What is stored of an analysis, under the column names pending_listings and vehicles share."""
    equipment = list(data.get("key_equipment") or [])
    if data.get("has_panoramic_roof") and not any("dach" in str(x).lower() or "szyber" in str(x).lower() for x in equipment):
        equipment.append("Dach panoramiczny/szyberdach")
    interior = " / ".join(x for x in (data.get("interior_color"), data.get("interior_material")) if x) or None
    return {"ai_summary": data.get("summary"), "ai_suggested_market": data.get("origin_market"),
            "ai_reasoning": data.get("origin_reasoning"), "ai_equipment": json.dumps(equipment, ensure_ascii=False),
            "ai_interior_color": interior}


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

def ollama_ready() -> bool:
    try:
        requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=5).raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Ollama nie odpowiada pod {OLLAMA_URL}: {e}")
        return False


MAX_ERRORS_IN_A_ROW = 5   # Ollama gone or the model unloadable: stop instead of failing every car


def enrich_ads(db, limit=None):
    """Per-ad analysis of the listings waiting in the review queue (shown on its detail page)."""
    rows = db.execute("""
        SELECT id, vin, raw_title, raw_description, origin_market, make, model, location_city, source, source_listing_id
        FROM pending_listings
        WHERE ai_summary IS NULL AND status = 'pending' AND length(raw_description) > 30
        ORDER BY id ASC
    """).fetchall()[:limit]
    print(f"Kolejka: {len(rows)} ogłoszeń bez analizy.")
    errors = 0
    for idx, r in enumerate(rows, 1):
        print(f"\n[ogłoszenie {idx}/{len(rows)}] ID {r['id']} | {r['make']} {r['model']} ({r['vin']})")
        try:
            data = analyze_with_bielik(r["raw_title"] or "", r["raw_description"], r["make"] or "", r["model"] or "",
                                       city=r["location_city"] or "")
        except Exception as e:
            print(f"  ❌ Błąd: {e}")
            errors += 1
            if errors >= MAX_ERRORS_IN_A_ROW:
                print(f"  {errors} błędów z rzędu, przerywam.")
                return False
            continue
        errors = 0
        f = stored_fields(data)
        region = REGION_NAME_TO_CODE.get(str(data.get("location_region") or "").strip().lower()) \
            or CITY_TO_REGION.get(r["location_city"] or "")
        db.execute("""
            UPDATE pending_listings
            SET ai_summary = ?, ai_suggested_market = ?, ai_conflict = ?, ai_reasoning = ?, ai_equipment = ?,
                ai_interior_color = ?, location_region = COALESCE(location_region, ?), ai_processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (f["ai_summary"], f["ai_suggested_market"], int(markets_conflict(r["origin_market"], f["ai_suggested_market"])),
              f["ai_reasoning"], f["ai_equipment"], f["ai_interior_color"], region, r["id"]))
        if region and r["source"] and r["source_listing_id"]:
            db.execute("UPDATE listing_observations SET location_region = COALESCE(location_region, ?) "
                       "WHERE source = ? AND source_listing_id = ?", (region, r["source"], r["source_listing_id"]))
        db.commit()
        print(f"  ✓ Rynek: {f['ai_suggested_market'] or 'brak'} | {f['ai_summary']}")
    return True


def cars_to_analyze(db):
    """Cars never analysed, or with an ad newer than their analysis."""
    return db.execute("""
        SELECT v.vin, v.make, v.model, v.origin_market, v.origin_checked_at, v.ai_processed_at,
               MAX(p.scraped_at) AS newest_ad
        FROM vehicles v JOIN pending_listings p ON p.vin = v.vin
        WHERE p.status IN ('approved', 'pending') AND length(p.raw_description) > 30
        GROUP BY v.vin
        HAVING v.ai_processed_at IS NULL OR MAX(p.scraped_at) > v.ai_processed_at
        ORDER BY v.vin
    """).fetchall()


def save_car(db, car, fields: dict, ad_count: int):
    # A market a person confirmed on the origin review page is not questioned again
    conflict = int(not car["origin_checked_at"] and markets_conflict(car["origin_market"], fields["ai_suggested_market"]))
    db.execute("""
        UPDATE vehicles
        SET ai_summary = ?, ai_suggested_market = ?, ai_conflict = ?, ai_reasoning = ?, ai_equipment = ?,
            ai_interior_color = ?, ai_ad_count = ?, ai_processed_at = CURRENT_TIMESTAMP,
            color_int = CASE WHEN ? = 0 THEN COALESCE(color_int, ?) ELSE color_int END
        WHERE vin = ?
    """, (fields["ai_summary"], fields["ai_suggested_market"], conflict, fields["ai_reasoning"], fields["ai_equipment"],
          fields["ai_interior_color"], ad_count, conflict, fields["ai_interior_color"], car["vin"]))
    db.commit()
    return conflict


def enrich_cars(db, limit=None):
    """One analysis per car, from all its ads at once. A car with one ad text that already has its
    per-ad analysis gets that copied, without asking Bielik again."""
    cars = cars_to_analyze(db)[:limit]
    print(f"Auta: {len(cars)} do analizy.")
    errors, asked, copied, conflicts = 0, 0, 0, 0
    started = time.time()
    for idx, car in enumerate(cars, 1):
        ads = db.execute("""
            SELECT source, scraped_at, raw_title, raw_description, location_city, ai_summary, ai_suggested_market,
                   ai_reasoning, ai_equipment, ai_interior_color
            FROM pending_listings
            WHERE vin = ? AND status IN ('approved', 'pending') AND length(raw_description) > 30
            ORDER BY scraped_at DESC
        """, (car["vin"],)).fetchall()
        texts = distinct_ads(ads)
        if not texts:
            continue
        if len(texts) == 1 and texts[0]["ai_summary"]:
            fields = {k: texts[0][k] for k in ("ai_summary", "ai_suggested_market", "ai_reasoning", "ai_equipment",
                                               "ai_interior_color")}
            conflicts += save_car(db, car, fields, len(ads))
            copied += 1
            continue
        eta = ""
        if asked:
            left = (time.time() - started) / asked * (len(cars) - idx + 1)
            eta = f" | zostało ok. {left / 3600:.1f} h"
        print(f"\n[auto {idx}/{len(cars)}] {car['make']} {car['model']} {car['vin']} | {len(texts)} opis(y){eta}")
        try:
            data = analyze_car(texts, car["make"] or "", car["model"] or "")
        except Exception as e:
            print(f"  ❌ Błąd: {e}")
            errors += 1
            if errors >= MAX_ERRORS_IN_A_ROW:
                print(f"  {errors} błędów z rzędu, przerywam.")
                break
            continue
        errors = 0
        asked += 1
        fields = stored_fields(data)
        if save_car(db, car, fields, len(ads)):
            conflicts += 1
            print(f"  ⚠️ Rynek w bazie '{car['origin_market']}', Bielik '{fields['ai_suggested_market']}': {fields['ai_reasoning']}")
        print(f"  ✓ Rynek: {fields['ai_suggested_market'] or 'brak'} | {fields['ai_summary']}")
    print(f"\nAuta: {asked} przeanalizowane przez Bielika, {copied} przepisane z jedynego ogłoszenia, "
          f"{conflicts} z innym rynkiem niż w bazie.")


def main():
    """python enrich_with_bielik.py [--limit N]: the review queue's ads, then the cars (see above)."""
    import sys
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    print(f"=== Bielik ({MODEL_NAME}) ===")
    if not ollama_ready():
        return
    db = get_db()
    if enrich_ads(db, limit):
        enrich_cars(db, limit)
    db.close()


if __name__ == "__main__":
    main()
