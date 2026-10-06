"""Porsche Cayman 981 (2013-2016).
Flat-6 2.7L, 3.4L.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "Cayman",
    variant = "Cayman 981",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/cayman"
        "?search%5Bfilter_float_year%3Afrom%5D=2013"
        "&search%5Bfilter_float_year%3Ato%5D=2016"
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
