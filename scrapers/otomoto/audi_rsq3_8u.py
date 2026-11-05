"""Audi RS Q3 8U (2013–2018) — run directly to scrape.

2.5 TFSI, 5 cylinders, 310-367 HP, quattro, S tronic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run


def is_8u(detail: dict) -> bool:
    return (detail.get("vin") or "").upper()[6:8] != "F3"


CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS Q3",
    variant = "RS Q3 8U",
    source  = "otomoto",
    model_id = "rsq3_8u",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/rs-q3"
        "?search%5Bfilter_float_year%3Ato%5D=2018"
        "&page={page}"
    ),
    validator = is_8u,
    defaults = {
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
