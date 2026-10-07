"""Mercedes A45 AMG W176 (2013-2018).
2.0L inline-4 turbo, 360-381 HP, AWD 4MATIC.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from scrapers.base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa A",
    variant = "A45 AMG W176",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/klasa-a"
        "?search%5Bfilter_float_year%3Afrom%5D=2016"
        "&search%5Bfilter_float_year%3Ato%5D=2018"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=380"
        "&search%5Bfilter_float_engine_power%3Ato%5D=390"
        "&page={page}"
    ),
    title_must_contain = ["a45", "a 45", "45 amg", "45amg"],
    title_must_not_contain = ["cla", "gla"],
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
