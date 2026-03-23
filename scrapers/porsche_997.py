"""Porsche 911 997 (2004–2012) — run directly to scrape.

997.1 = 2004–2008, 997.2 = 2008–2012.
Carrera: 325 HP (3.6), Carrera S: 355 HP (3.8), Turbo: 480/500 HP.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "911",
    variant = "997",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/911"
        "?search%5Bfilter_float_year%3Afrom%5D=2004"
        "&search%5Bfilter_float_year%3Ato%5D=2012"
        "&page={page}"
    ),
    pages = 5,
    defaults = {
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
