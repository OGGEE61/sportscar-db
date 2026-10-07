"""Porsche Cayman GT4 981 (2015–2016) — run directly to scrape.

981 GT4: 3.8L flat-six (9A1), 385 HP, RWD, 6-speed manual only.
Naturally aspirated, mid-engine, no PDK option — driver's car.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "Cayman",
    variant = "981 GT4",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/cayman"
        "?search%5Bfilter_float_year%3Afrom%5D=2015"
        "&search%5Bfilter_float_year%3Ato%5D=2016"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=370"
        "&page={page}"
    ),
    title_must_contain = "GT4",
    title_must_not_contain = ["911", "carrera", "macan", "panamera", "cayenne", "taycan"],
    defaults = {
        "power_hp":     385,
        "engine_cc":    3800,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
