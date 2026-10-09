"""Audi R8 V8 (2006-2015).
4.2 FSI V8, 420-430 HP, AWD quattro.
"""
import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(os.path.dirname(_dir)) if "scrapers_to_be_verified" in _dir else os.path.dirname(_dir)
if _root not in sys.path: sys.path.insert(0, _root)
_scrapers = os.path.join(_root, "scrapers")
if _scrapers not in sys.path: sys.path.insert(0, _scrapers)
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "R8",
    variant = "R8 V8",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/r8"
        "?search%5Bfilter_float_engine_capacity%3Ato%5D=4500"
        "&page={page}"
    ),
    title_must_contain = None,
    defaults = {
        "power_hp":     420,
        "engine_cc":    4163,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "semi-auto",
        "drivetrain":   "AWD",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
