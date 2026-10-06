"""BMW 135i E82/E88 (2007-2013)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "Seria 1",
    variant = "135i E82/E88",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/seria-1"
        "?search%5Bfilter_float_engine_power%3Afrom%5D=300"
        "&search%5Bfilter_float_year%3Afrom%5D=2007"
        "&search%5Bfilter_float_year%3Ato%5D=2013"
        "&page={page}"
    ),
    title_must_contain = "135i",
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
