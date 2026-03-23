"""Audi RS3 8V facelift (2017–2020) — run directly to scrape."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS3",
    variant = "8V",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/audi/rs3"
        "?search%5Bfilter_float_year%3Afrom%5D=2017"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    pages = 5,
    defaults = {
        "power_hp":     400,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "doors":        4,
    },
)

if __name__ == "__main__":
    run(CONFIG)
