"""Mercedes S55 AMG W220 (1999-2005).
5.4 V8 Kompressor (or NA early on), 360-500 HP, RWD.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa S",
    variant = "S55 AMG W220",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/klasa-s"
        "?search%5Bfilter_float_engine_capacity%3Afrom%5D=5300"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=5600"
        "&page={page}"
    ),
    title_must_contain = "s55",
    defaults = {
        "power_hp":     500,
        "engine_cc":    5439,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
        "body_type":    "Sedan",
    }
)

if __name__ == "__main__":
    run(CONFIG)
