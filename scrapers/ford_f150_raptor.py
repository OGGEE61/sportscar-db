"""Ford F-150 Raptor & Raptor R.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Ford",
    model   = "F150",
    variant = "Raptor",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/ford/f150"
        "?search%5Bfilter_float_power%3Afrom%5D=440"
        "&page={page}"
    ),
    title_must_contain = "raptor",
    defaults = {
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "Pickup",
    }
)

if __name__ == "__main__":
    run(CONFIG)
