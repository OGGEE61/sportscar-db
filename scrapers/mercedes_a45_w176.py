"""Mercedes A45 AMG W176 (2013-2018).
2.0L inline-4 turbo, 360-381 HP, AWD 4MATIC.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa A",
    variant = "A45 AMG W176",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/klasa-a"
        "?search%5Bfilter_enum_generation%5D=gen-w176-2012-2018"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=350"
        "&page={page}"
    ),
    title_must_contain = None,
    defaults = {
        "power_hp":     381,
        "engine_cc":    1991,
        "engine_cyl":   4,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "Hatchback",
    }
)

if __name__ == "__main__":
    run(CONFIG)
