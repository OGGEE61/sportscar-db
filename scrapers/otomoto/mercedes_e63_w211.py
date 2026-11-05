"""Mercedes-Benz E63 AMG W211 (2006–2009) — run directly to scrape.

6.2 V8 M156, 514 HP, RWD. Otomoto cards are often titled just "Klasa E", so year, engine size and
power find it. Up to 520 HP leaves out the 525 HP W212 E63 with the same engine from 2009; the VIN
rejects any that gets through.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_other_mercedes_chassis


def is_w211(detail: dict) -> bool:
    return not is_other_mercedes_chassis(detail.get("vin"), "211")


CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa E",
    variant = "W211 E63 AMG",
    source  = "otomoto",
    model_id = "e63_w211",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/e-klasa"
        "?search%5Bfilter_float_year%3Afrom%5D=2006"
        "&search%5Bfilter_float_year%3Ato%5D=2009"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=6000"
        "&search%5Bfilter_float_engine_power%3Ato%5D=520"
        "&page={page}"
    ),
    validator = is_w211,
    defaults = {
        "power_hp":     514,
        "engine_cc":    6208,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
