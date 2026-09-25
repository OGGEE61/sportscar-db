"""BMW X3 M F97 (2019–2024) — run directly to scrape.

F97 = X3 M (S58 3.0 biturbo engine, 480/510 HP).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3 M",
    variant = "F97",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/x3-m"
        "?search%5Bfilter_float_year%3Afrom%5D=2019"
        "&search%5Bfilter_float_year%3Ato%5D=2024"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=450"
        "&search%5Bfilter_enum_fuel_type%5D=petrol"
        "&page={page}"
    ),
    min_year = 2019,
    max_year = 2024,
    pages = 5,
    defaults = {
        "power_hp":     510,
        "engine_cc":    2993,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
