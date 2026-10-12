"""BMW X3 M F97 (OLX) — run directly to scrape.

Hits OLX's BMW X3-M category. Strictly isolates genuine X3 M F97 models
(S58 3.0 biturbo, 480/510 HP Competition) and rejects M40i, M40d, 2.0d/3.0d, and non-VIN listings.
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run


def validate_x3m(detail: dict) -> bool:
    """Strict validator for authentic BMW X3 M (F97) vehicles.

    1. VIN is strictly required.
    2. Must be petrol (exclude diesel, e.g. M40d).
    3. Reject M40i / M40d / 2.0d / 3.0d accidentally categorized under X3 M.
    4. Power must match true X3 M (>= 440 HP; S58 produces 480/510 HP).
    """
    vin = (detail.get("vin") or "").strip().upper()
    if not vin or len(vin) < 11:
        print(f"  [reject-x3m] Brak poprawnego VIN (otrzymano: '{vin or 'BRAK'}') — odrzucono.")
        return False

    fuel = (detail.get("fuel_type") or "").lower()
    if "diesel" in fuel:
        print(f"  [reject-x3m] Paliwo diesel wykluczone dla X3 M — odrzucono.")
        return False

    title = (detail.get("title") or "").lower()
    desc = (detail.get("raw_description") or "").lower()

    if any(k in title for k in ["m40i", "m40d", "m40", "2.0d", "3.0d", "x-line", "xline"]):
        print(f"  [reject-x3m] Odrzucono wersję niebędącą X3 M ('{title}')")
        return False

    power = detail.get("power_hp") or 0
    if power and power < 440:
        print(f"  [reject-x3m] Moc {power} KM < 440 KM (nie jest X3 M) — odrzucono.")
        return False

    return True


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3 M",
    variant = "F97",
    source  = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/x3-m/"
        "?search[filter_float_year:from]=2019"
        "&search[filter_float_year:to]=2024"
        "&search[filter_float_price:from]=100000"
        "&page={page}"
    ),
    min_year = 2019,
    max_year = 2024,
    title_must_not_contain = ["M40i", "M40d", "M40"],
    validator = validate_x3m,
    defaults = {
        "power_hp":     510,
        "engine_cc":    2993,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
