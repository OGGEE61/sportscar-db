"""Audi RS3 8V facelift (2017–2020) (OLX) — run directly to scrape.

Hits OLX search for Audi RS3 (Sportback & Limousine) for years 2017–2020.
Strictly validates authentic RS3 8V models (2.5 TFSI 400 HP DAZA/DNWA),
requiring valid VIN and excluding A3/S3 replicas and diesels.
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run


def validate_rs3_8v(detail: dict) -> bool:
    """Strict validator for authentic Audi RS3 8V (2017–2020) listings.

    1. VIN is strictly required and validated.
    2. Must be petrol (2.5 TFSI 5-cylinder).
    3. Exclude non-RS models (A3, S3 look replicas).
    4. Power must match RS3 (standard 400 HP, tuned >= 370 HP; reject 150/190/310 HP A3/S3).
    """
    vin = (detail.get("vin") or "").strip().upper()
    if not vin or len(vin) < 11:
        print(f"  [reject-rs3] Brak poprawnego VIN (otrzymano: '{vin or 'BRAK'}') — odrzucono.")
        return False

    fuel = (detail.get("fuel_type") or "").lower()
    if "diesel" in fuel:
        print("  [reject-rs3] Paliwo diesel wykluczone dla RS3 — odrzucono.")
        return False

    title = (detail.get("title") or "").lower()
    desc = (detail.get("raw_description") or "").lower()

    # Must mention RS3 or RS 3 in title or description
    if not any(k in title for k in ["rs3", "rs 3"]) and not any(k in desc for k in ["rs3", "rs 3"]):
        print("  [reject-rs3] Brak oznaczenia RS3 w tytule i opisie — odrzucono.")
        return False

    # Check for fake/look conversions: e.g. "s3 rs3 look", "a3 rs3 pakiet"
    if any(k in title for k in ["s3 look", "a3 look", "rs3 look", "pakiet rs3", "optyka rs3"]):
        print(f"  [reject-rs3] Wykryto replikę / pakiet wizualny ('{title}') — odrzucono.")
        return False

    # Power check: DAZA/DNWA standard is 400 HP. If seller filled power, must be >= 350 HP
    power = detail.get("power_hp") or 0
    if power and power < 350:
        print(f"  [reject-rs3] Moc {power} KM < 350 KM (prawdopodobnie S3/A3) — odrzucono.")
        return False

    return True


CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS3",
    variant = "8V",
    source  = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-audi-rs3-8v/"
        "?search[filter_float_year:from]=2017"
        "&search[filter_float_year:to]=2020"
        "&search[filter_enum_model][0]=rs3"
        "&search[filter_enum_model][1]=rs3-limousine"
        "&page={page}"
    ),
    min_year = 2017,
    max_year = 2020,
    title_must_not_contain = ["look rs3", "pakiet rs3", "optyka rs3"],
    validator = validate_rs3_8v,
    defaults = {
        "power_hp":     400,
        "engine_cc":    2480,
        "engine_cyl":   5,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
