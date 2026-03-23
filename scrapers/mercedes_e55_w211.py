"""Mercedes-Benz E55 AMG W211 (2003–2006) — run directly to scrape.

W211 E55 AMG: 5.5L V8 Kompressor (M113K), 476 HP, RWD, 5-speed automatic.
otomoto has no dedicated E55 slug so we filter by year + power > 460 HP
and guard with title keyword.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa E",
    variant = "W211 E55 AMG",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/klasa-e"
        "?search%5Bfilter_float_year%3Afrom%5D=2003"
        "&search%5Bfilter_float_year%3Ato%5D=2006"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=460"
        "&page={page}"
    ),
    title_must_contain = "Klasa E 55",
    pages = 5,
    defaults = {
        "power_hp":     476,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
