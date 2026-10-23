"""BMW X3 M40i G01 (autoplac.pl) — run directly to scrape.

Shares its searches with the X3 M F97 scraper; the VIN decides which of the two a
car is (see _x3_g01.py), so a mislabeled car is saved under the right model instead
of being rejected. Cars without a VIN go through the OLX M40i validator (rejected).
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run
from olx.bmw_x3_m40i_g01 import validate_x3_m40i
from autoplac._x3_g01 import X3_G01_URLS, reassign_x3_g01


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3",
    variant = "M40i G01",
    source  = "autoplac",
    list_url = X3_G01_URLS,
    min_year = 2017,
    max_year = 2024,
    title_must_not_contain = ["M40d", "M40 d", "diesel"],
    validator = validate_x3_m40i,
    reassign = reassign_x3_g01,
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
