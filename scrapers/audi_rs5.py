"""Audi RS5 B8/B9 (up to 2020) — run directly to scrape.

B8  = 2010–2016 (4.2 V8 FSI, 450 HP)
B9  = 2017–2020 (2.9 TFSI biturbo, 450 HP)
Both variants: petrol, AWD, automatic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS5",
    variant = "B8/B9",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/rs5"
        "?search%5Bfilter_float_year%3Ato%5D=2020"
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
