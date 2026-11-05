"""Audi RS Q3 F3 (2019–) — run directly to scrape.

2.5 TFSI, 5 cylinders, 400 HP, quattro, S tronic. Still sold new, so dealer stock is left out
the same way as for the M2 G87.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_dealer_new


def used_f3(detail: dict) -> bool:
    if (detail.get("vin") or "").upper()[6:8] == "8U":
        return False
    return not is_dealer_new(detail.get("year"), detail.get("mileage_km"),
                             detail.get("first_registration_date"))


CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS Q3",
    variant = "F3",
    source  = "otomoto",
    model_id = "rsq3_f3",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/rs-q3"
        "?search%5Bfilter_float_year%3Afrom%5D=2019"
        "&page={page}"
    ),
    validator = used_f3,
    defaults = {
        "power_hp":     400,
        "engine_cc":    2480,
        "engine_cyl":   5,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
