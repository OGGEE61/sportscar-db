"""BMW M2 F87 (2016–2021) — run directly to scrape.

F87 M2: 3.0L N55 (370 HP, 2016-2018) or S55 Competition (410 HP, 2018-2021).
Pure RWD, 6-speed manual or 7-speed DCT.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "M2",
    variant = "F87",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m2"
        "?search%5Bfilter_float_year%3Afrom%5D=2016"
        "&search%5Bfilter_float_year%3Ato%5D=2021"
        "&page={page}"
    ),
    title_must_contain = "M2",
    defaults = {
        "power_hp":     370,
        "engine_cc":    2979,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
