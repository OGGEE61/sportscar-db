"""BMW 135i E82/E88 (2007-2013)
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
    model   = "Seria 1",
    variant = "135i E82/E88",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/seria-1"
        "?search%5Bfilter_enum_fuel_type%5D=petrol"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=2950"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=3050"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=300"
        "&search%5Bfilter_float_year%3Afrom%5D=2007"
        "&search%5Bfilter_float_year%3Ato%5D=2013"
        "&page={page}"
    ),
    title_must_contain = None,
    title_must_not_contain = ["1M", "1 M"],
    defaults = {
        "power_hp":     306,
        "engine_cc":    2979,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
