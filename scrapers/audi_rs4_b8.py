"""Audi RS4 B8 / B8.5 (2012–2015) — run directly to scrape.

B8/B8.5 RS4: 4.2 V8 FSI naturally aspirated, 450 HP, AWD, automatic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS4",
    variant = "B8",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/rs4"
        "?search%5Bfilter_float_year%3Afrom%5D=2012"
        "&search%5Bfilter_float_year%3Ato%5D=2015"
        "&page={page}"
    ),
    pages = 5,
    defaults = {
        "power_hp":     450,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
