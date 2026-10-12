"""BMW X3 M40i G01 (OLX) — run directly to scrape.

Hits OLX's BMW X3 query for 'm40i' (2017–2024). Filters out diesel M40d,
smaller 20i/30i models, and full X3 M Competition models.
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run


def validate_x3_m40i(detail: dict) -> bool:
    """Strict validator for authentic BMW X3 M40i (G01) vehicles.

    1. VIN is strictly required.
    2. Must be petrol (exclude diesel M40d).
    3. Must be M40i (not 20i, 30i, 20d, 30d).
    4. Power must match B58 (340–400 HP; reject 184/252 HP 4-cyl and 510 HP S58).
    """
    vin = (detail.get("vin") or "").strip().upper()
    if not vin or len(vin) < 11:
        print(f"  [reject-m40i] Brak poprawnego VIN (otrzymano: '{vin or 'BRAK'}') — odrzucono.")
        return False

    fuel = (detail.get("fuel_type") or "").lower()
    desc = (detail.get("raw_description") or "").lower()
    title = (detail.get("title") or "").lower()

    if "diesel" in fuel or "diesel" in desc or "m40d" in title or "m40d" in desc or "m40 d" in title:
        print(f"  [reject-m40i] Wykryto wersję wysokoprężną (diesel / M40d) — odrzucono.")
        return False

    # Title or description sanity check: must explicitly reference M40i / M40
    if not any(k in title for k in ["m40i", "m40", "m 40i", "m 40"]):
        if not ("m40i" in desc or "m40" in desc):
            print(f"  [reject-m40i] Brak oznaczenia M40i w tytule i opisie — odrzucono.")
            return False

    # Power range check: B58 has 354-388 HP. Reject 20i/30i and X3 M (>430 HP)
    power = detail.get("power_hp") or 0
    if power and (power > 430 or power < 320):
        print(f"  [reject-m40i] Moc {power} KM poza zakresem B58 M40i (320-430 KM) — odrzucono.")
        return False

    # Exclude true X3 M Competition
    if any(k in title for k in ["x3m comp", "competition"]):
        if power and power > 440:
            print(f"  [reject-m40i] Wykryto pełne X3 M Competition — odrzucono (to nie M40i).")
            return False

    return True


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3",
    variant = "M40i G01",
    source  = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/x3/q-m40i/"
        "?search[filter_float_year:from]=2017"
        "&search[filter_float_year:to]=2024"
        "&search[filter_float_price:from]=100000"
        "&page={page}"
    ),
    min_year = 2017,
    max_year = 2024,
    title_must_not_contain = ["M40d", "M40 d", "diesel"],
    validator = validate_x3_m40i,
    defaults = {
        "power_hp":     360,
        "engine_cc":    2998,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
