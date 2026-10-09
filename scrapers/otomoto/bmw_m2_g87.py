"""BMW M2 G87 (2022–) — run directly to scrape.

G87 M2: 3.0L S58 twin-turbo inline-6, 460 HP, RWD.
6-speed manual or 8-speed torque-converter auto.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "M2",
    variant = "G87",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m2"
        "?search%5Bfilter_float_year%3Afrom%5D=2022"
        "&page={page}"
    ),
    title_must_contain = "M2",
    defaults = {
        "power_hp":     460,
        "engine_cc":    2993,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
