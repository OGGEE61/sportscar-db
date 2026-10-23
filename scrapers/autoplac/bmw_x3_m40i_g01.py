"""BMW X3 M40i G01 (autoplac.pl) — run directly to scrape.

Full-text search for 'bmw x3 m40' (also returns M40d); the OLX validator keeps
only petrol B58 M40i. autoplac shows the VIN and plate without login.
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run
from olx.bmw_x3_m40i_g01 import validate_x3_m40i


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3",
    variant = "M40i G01",
    source  = "autoplac",
    list_url = "https://autoplac.pl/oferty/samochody-osobowe?fullTextQuery=bmw%20x3%20m40&p={page}",
    min_year = 2017,
    max_year = 2024,
    title_must_not_contain = ["M40d", "M40 d", "diesel"],
    validator = validate_x3_m40i,
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
