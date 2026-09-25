"""BMW X3 M40i G01 (2017–2024) — run directly to scrape.

G01 = X3 M40i (B58 3.0 turbo engine, 354/360 HP).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3",
    variant = "M40i G01",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/x3"
        "?search%5Bfilter_float_year%3Afrom%5D=2017"
        "&search%5Bfilter_float_year%3Ato%5D=2024"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=340"
        "&search%5Bfilter_float_engine_power%3Ato%5D=370"
        "&page={page}"
    ),
    min_year = 2017,
    max_year = 2024,
    pages = 5,
    defaults = {
        "power_hp":     360,
        "engine_cc":    2998,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
