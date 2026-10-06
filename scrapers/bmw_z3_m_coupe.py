"""BMW Z3 M Coupe (1998-2002) - Clown Shoe
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "Z3",
    variant = "Z3 M Coupe",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/z3"
        "?search%5Bfilter_float_engine_power%3Afrom%5D=300"
        "&page={page}"
    ),
    defaults = {
        "power_hp":     321,
        "engine_cc":    3201,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
