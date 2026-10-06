"""Porsche 718 Cayman (2016-).
Flat-4 turbo or Flat-6.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "718",
    variant = "718 Cayman",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/porsche/718"
        "?search%5Bfilter_enum_body_type%5D=coupe"
        "&page={page}"
    ),
    title_must_contain = ["gts", "gt4"],
    defaults = {
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
