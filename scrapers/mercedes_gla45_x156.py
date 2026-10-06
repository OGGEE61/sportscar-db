"""Mercedes GLA45 AMG X156 (2014-2019).
2.0L inline-4 turbo, 360-381 HP, AWD 4MATIC.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "GLA",
    variant = "GLA45 AMG X156",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/gla"
        "?search%5Bfilter_enum_generation%5D=gen-x156-2014"
        "&search%5Bfilter_float_power%3Afrom%5D=350"
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
        "body_type":    "SUV",
    }
)

if __name__ == "__main__":
    run(CONFIG)
