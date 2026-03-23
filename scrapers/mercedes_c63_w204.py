"""Mercedes-Benz C63 AMG W204 (2008–2015) — run directly to scrape.

W204 C63 AMG: 6.2 V8 M156, 457 HP (standard) / 487 HP (Black Series/Performance).
otomoto has a direct C63 model filter so no title keyword guard needed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa C",
    variant = "W204 C63 AMG",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/klasa-c/c63-amg"
        "?search%5Bfilter_float_year%3Afrom%5D=2008"
        "&search%5Bfilter_float_year%3Ato%5D=2015"
        "&page={page}"
    ),
    pages = 5,
    defaults = {
        "power_hp":     457,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
