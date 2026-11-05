"""Mercedes-Benz E63 AMG W212 (2009–2016) — run directly to scrape.

6.2 V8 M156 (525 HP) or 5.5 V8 biturbo M157 (525-585 HP), RWD or 4MATIC. Over 520 HP and 5.4+ litres
leave out the E500, the E400 and the 514 HP W211 E63.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_other_mercedes_chassis


def is_w212(detail: dict) -> bool:
    return not is_other_mercedes_chassis(detail.get("vin"), "212")


CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa E",
    variant = "W212 E63 AMG",
    source  = "otomoto",
    model_id = "e63_w212",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/e-klasa"
        "?search%5Bfilter_enum_generation%5D=gen-w212-2009"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=5400"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=521"
        "&page={page}"
    ),
    min_year = 2009,
    max_year = 2016,
    validator = is_w212,
    defaults = {
        "power_hp":     557,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
    },
)

if __name__ == "__main__":
    run(CONFIG)
