import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Porsche 718 Cayman (2016-).
Flat-4 turbo or Flat-6.
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "718",
    variant = "718 Cayman",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/718-cayman"
        "?search%5Bfilter_float_engine_power%3Afrom%5D=345"
        "&page={page}"
    ),
    title_must_contain = ["cayman"],
    title_must_not_contain = ["boxster", "911", "carrera", "macan", "panamera", "cayenne", "taycan"],
    defaults = {
        "power_hp":     350,
        "engine_cc":    2497,
        "engine_cyl":   4,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
