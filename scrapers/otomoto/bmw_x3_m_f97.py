"""BMW X3 M F97 (2019–2024) — run directly to scrape.

F97 = X3 M (S58 3.0 biturbo engine, 480/510 HP).

Shares its searches with the X3 M40i scraper; the VIN decides which of the two a
car is (see x3_g01.py), so an M40i badged as X3 M is saved as an M40i, not rejected.
Cars without a VIN are kept only if their power fits an X3 M.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from x3_g01 import reassign_x3_g01, x3_g01_power_validator
from otomoto.bmw_x3_m40i_g01 import X3_G01_URLS

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3 M",
    variant = "F97",
    source  = "otomoto",
    list_url = X3_G01_URLS,
    min_year = 2019,
    max_year = 2024,
    validator = x3_g01_power_validator("X3 M"),
    reassign = reassign_x3_g01("otomoto"),
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
