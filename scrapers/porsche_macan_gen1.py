"""Porsche Macan Gen 1 (2014-2020) - S / GTS / Turbo.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "Macan",
    variant = "Macan Gen 1 (S/GTS/Turbo)",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/macan"
        "?search%5Bfilter_float_year%3Ato%5D=2020"
        "&search%5Bfilter_float_power%3Afrom%5D=330"
        "&page={page}"
    ),
    title_must_contain = None,
    defaults = {
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    }
)

if __name__ == "__main__":
    run(CONFIG)
