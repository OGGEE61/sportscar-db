"""Ford Ranger Raptor.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Ford",
    model   = "Ranger",
    variant = "Ranger Raptor",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/ford/ranger"
        "?search%5Bfilter_float_engine_capacity%3Afrom%5D=2900"
        "&page={page}"
    ),
    title_must_contain = "raptor",
    defaults = {
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "Pickup",
    }
)

if __name__ == "__main__":
    run(CONFIG)
