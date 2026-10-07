"""RAM 1500 TRX (2021-).
6.2L Supercharged V8, 702 HP, AWD.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "RAM",
    model   = "1500",
    variant = "TRX",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/ram"
        "?search%5Bfilter_float_engine_power%3Afrom%5D=700"
        "&page={page}"
    ),
    title_must_contain = ["trx"],
    defaults = {
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "Pickup",
    }
)

if __name__ == "__main__":
    run(CONFIG)
