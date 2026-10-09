"""Audi TT RS (8J & 8S generations, 2009–) — run directly to scrape.

8J TT RS (2009-2014): 2.5L inline-5 DOHC turbo, 340 HP, AWD quattro.
8S TT RS (2016-2023): 2.5L inline-5 TFSI, 400 HP, AWD quattro.
Coupe and Roadster variants exist.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "TT",
    variant = "TT RS",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/tt-rs"
        "?search%5Bfilter_float_year%3Afrom%5D=2009"
        "&page={page}"
    ),
    title_must_contain = None,
    defaults = {
        "power_hp":     400,
        "engine_cc":    2480,
        "engine_cyl":   5,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
