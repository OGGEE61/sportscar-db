"""Mercedes SL55 AMG R230 (2001-2008).
5.4 V8 Kompressor, 476-517 HP, RWD.
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "SL",
    variant = "SL55 AMG R230",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/sl-klasa/r230-2001-2012"
        "?search%5Bfilter_float_year%3Ato%5D=2008"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=5300"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=5600"
        "&page={page}"
    ),
    title_must_contain = ["sl55", "sl 55", "55 amg", "55amg"],
    title_must_not_contain = [
        "c55", "c 55", "e55", "e 55", "cls55", "cls 55", "s55", "s 55",
        "slk55", "slk 55", "clk55", "clk 55", "g55", "g 55", "sl500", "sl 500",
        "sl600", "sl 600", "sl63", "sl 63", "sl65", "sl 65", "sl350", "sl 350"
    ],
    defaults = {
        "power_hp":     500,
        "engine_cc":    5439,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
        "body_type":    "Kabriolet",
    }
)

if __name__ == "__main__":
    run(CONFIG)
