"""Porsche Cayman 987 (2005-2012).
Flat-6 2.7L, 2.9L, 3.4L.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "Cayman",
    variant = "Cayman 987",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/cayman"
        "?search%5Bfilter_float_year%3Ato%5D=2012"
        "&page={page}"
    ),
    title_must_contain = ["gts", "gt4"],
    defaults = {
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
