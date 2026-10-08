"""Mercedes-Benz CLS 55 AMG C219 (2004–2006) — run directly to scrape.

C219 CLS 55 AMG: 5.4L V8 Kompressor (M113K), 476 HP, RWD, 5-speed automatic.
otomoto has no dedicated CLS 55 slug so we filter by year + power > 460 HP
and guard with title keyword.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "CLS",
    variant = "C219 CLS 55 AMG",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/cls-klasa"
        "?search%5Bfilter_float_year%3Afrom%5D=2004"
        "&search%5Bfilter_float_year%3Ato%5D=2006"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=460"
        "&page={page}"
    ),
    title_must_contain = "CLS 55",
    defaults = {
        "power_hp":     476,
        "engine_cc":    5439,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG)
