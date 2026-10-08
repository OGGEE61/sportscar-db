"""Mercedes GLA45 AMG X156 (2014-2019).
2.0L inline-4 turbo, 360-381 HP, AWD 4MATIC.
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "GLA",
    variant = "GLA45 AMG X156",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/gla-klasa"
        "?search%5Bfilter_float_year%3Afrom%5D=2016"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=350"
        "&page={page}"
    ),
    title_must_contain = ["gla"],
    title_must_not_contain = ["cla", "klasa a", "gle", "gls", "klasa c", "klasa s", "c 43"],
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
