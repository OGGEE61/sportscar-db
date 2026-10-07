"""BMW M3 E46 (2000-2006)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "M3",
    variant = "E46 M3",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m3"
        "?search%5Bfilter_float_year%3Afrom%5D=2000"
        "&search%5Bfilter_float_year%3Ato%5D=2006"
        "&page={page}"
    ),
    defaults = {
        "power_hp":     343,
        "engine_cc":    3246,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
