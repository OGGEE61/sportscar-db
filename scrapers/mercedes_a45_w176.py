"""Mercedes A45 AMG W176 (2013-2018).
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
    model   = "Klasa A",
    variant = "A45 AMG W176",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/a-klasa"
        "?search%5Bfilter_float_year%3Afrom%5D=2016"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=370"
        "&page={page}"
    ),
    title_must_contain = ["amg 45", "45 amg", "a45", "a 45", "45amg", "klasa a"],
    title_must_not_contain = ["cla", "gla", "cls", "gle", "gls", "glc", "klasa c", "klasa s", "c 43", "c43", "c 63", "c63", "450", "a 35", "a35", "35 amg", "amg 35"],
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
