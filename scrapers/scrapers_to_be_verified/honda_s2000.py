"""Honda S2000 (1999-2009).
2.0L / 2.2L inline-4, RWD.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Honda",
    model   = "S2000",
    variant = "S2000",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/honda/s-2000"
        "?page={page}"
    ),
    title_must_contain = ["s2000", "s 2000"],
    defaults = {
        "engine_cyl":   4,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
        "body_type":    "Kabriolet",
    }
)

if __name__ == "__main__":
    run(CONFIG)
