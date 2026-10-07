"""BMW 1M E82 (2011-2012)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "Seria 1",
    variant = "1M E82",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/seria-1"
        "?search%5Bfilter_float_engine_power%3Afrom%5D=330"
        "&search%5Bfilter_float_year%3Afrom%5D=2010"
        "&search%5Bfilter_float_year%3Ato%5D=2013"
        "&search%5Bq%5D=1M"
        "&page={page}"
    ),
    title_must_contain = "1M",
    defaults = {
        "power_hp":     340,
        "engine_cc":    2979,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
