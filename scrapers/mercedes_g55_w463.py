"""Mercedes G55 AMG W463 (1999-2012).
5.4 V8 Kompressor (or NA early on), 354-507 HP, AWD.
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa G",
    variant = "G55 AMG W463",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/g-klasa"
        "?search%5Bfilter_float_year%3Ato%5D=2012"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=5300"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=5600"
        "&page={page}"
    ),
    title_must_contain = ["g55", "g 55", "55 amg", "55amg"],
    title_must_not_contain = [
        "g500", "g 500", "g63", "g 63", "g65", "g 65", "klasa s", "klasa e",
        "klasa c", "sl 55", "cls 55", "ml 55"
    ],
    defaults = {
        "power_hp":     500,
        "engine_cc":    5439,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    }
)

if __name__ == "__main__":
    run(CONFIG)
