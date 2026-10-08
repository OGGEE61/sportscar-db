"""BMW M5 E39 (1998-2003)
"""
import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(os.path.dirname(_dir)) if "scrapers_to_be_verified" in _dir else os.path.dirname(_dir)
if _root not in sys.path: sys.path.insert(0, _root)
_scrapers = os.path.join(_root, "scrapers")
if _scrapers not in sys.path: sys.path.insert(0, _scrapers)
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "M5",
    variant = "E39 M5",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m5"
        "?search%5Bfilter_float_year%3Afrom%5D=1998"
        "&search%5Bfilter_float_year%3Ato%5D=2003"
        "&page={page}"
    ),
    defaults = {
        "power_hp":     400,
        "engine_cc":    4941,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Sedan",
    },
)

if __name__ == "__main__":
    run(CONFIG)
