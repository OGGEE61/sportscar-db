"""BMW 1M E82 (2011-2012)
"""
import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(os.path.dirname(_dir)) if "scrapers_to_be_verified" in _dir else os.path.dirname(_dir)
if _root not in sys.path: sys.path.insert(0, _root)
_scrapers = os.path.join(_root, "scrapers")
if _scrapers not in sys.path: sys.path.insert(0, _scrapers)
from base_scraper import ScraperConfig, run

def validate_genuine_1m(detail: dict) -> bool:
    """Validate that the listing is an authentic factory BMW 1M Coupe (E82).
    
    1. Transmission: factory 1M was EXCLUSIVELY 6-speed manual (never automatic).
    2. VIN: genuine 1M VIN contains 'UR9' (EU) or '1LK' (USA). 135i has '1N9', 'UC7', 'UC9'.
    3. Price sanity: authentic 1M collector car does not sell for < 100k PLN.
    """
    # Check transmission
    trans = (detail.get("transmission") or "").lower()
    if any(k in trans for k in ["auto", "steptronic", "tiptronic"]):
        print(f"  [skip-fake-1m] Factory 1M was manual only (found transmission: {trans})")
        return False

    # Check VIN
    vin = (detail.get("vin") or "").upper()
    if vin:
        if any(bad in vin for bad in ["1N9", "UC7", "UC9", "WB3"]):
            print(f"  [skip-fake-1m] VIN {vin} belongs to 135i, not genuine 1M")
            return False
        if len(vin) == 17 and not any(good in vin for good in ["UR9", "1LK"]):
            print(f"  [skip-fake-1m] VIN {vin} does not match 1M pattern (UR9/1LK)")
            return False

    # Check price
    price = detail.get("price_from_detail")
    if price and price < 100000:
        print(f"  [skip-fake-1m] Price {price} PLN too low for genuine 1M")
        return False

    return True

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "Seria 1",
    variant = "1M E82",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/1m"
        "?search%5Bfilter_float_year%3Afrom%5D=2011"
        "&search%5Bfilter_float_year%3Ato%5D=2012"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=330"
        "&page={page}"
    ),
    title_must_contain = None,
    validator = validate_genuine_1m,
    defaults = {
        "power_hp":     340,
        "engine_cc":    2979,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
