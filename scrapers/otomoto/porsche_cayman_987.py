import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Porsche Cayman 987 (2005-2012).
Flat-6 2.7L, 2.9L, 3.4L.
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "Cayman",
    variant = "Cayman 987",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/cayman"
        "?search%5Bfilter_float_year%3Ato%5D=2012"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=290"
        "&page={page}"
    ),
    title_must_contain = ["cayman"],
    title_must_not_contain = ["boxster", "911", "carrera", "macan", "panamera", "cayenne", "taycan"],
    defaults = {
        "power_hp":     295,
        "engine_cc":    3387,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
