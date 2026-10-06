"""Nissan Patrol Y61 Super Safari (4.8 TB48DE).
Usually GCC spec.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Nissan",
    model   = "Patrol",
    variant = "Super Safari (4.8)",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/nissan/patrol"
        "?search%5Bfilter_float_engine_capacity%3Afrom%5D=4500"
        "&page={page}"
    ),
    title_must_contain = None,
    defaults = {
        "engine_cc":    4759,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    }
)

if __name__ == "__main__":
    run(CONFIG)
