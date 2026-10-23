"""BMW X3 M40i G01 (2017–2024) — run directly to scrape.

G01 = X3 M40i (B58 3.0 turbo engine, 354/360 HP).

Shares its searches with the X3 M F97 scraper; the VIN decides which of the two a
car is (see x3_g01.py), so a mislabeled car is saved under the right model instead
of being rejected. Cars without a VIN are kept only if their power fits an M40i.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from x3_g01 import reassign_x3_g01, x3_g01_power_validator

# Shared with the X3 M scraper. No upper power limit: the VIN tells the M40i from the X3 M,
# and both models are filed under 'x3' as well as 'x3-m'.
X3_G01_URLS = [
    (
        "https://www.otomoto.pl/osobowe/bmw/{model}"
        "?search%5Bfilter_float_year%3Afrom%5D=2017"
        "&search%5Bfilter_float_year%3Ato%5D=2024"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=340"
        "&search%5Bfilter_enum_fuel_type%5D=petrol"
        "&page={{page}}"
    ).format(model=model)
    for model in ("x3", "x3-m")
]

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "X3",
    variant = "M40i G01",
    source  = "otomoto",
    list_url = X3_G01_URLS,
    min_year = 2017,
    max_year = 2024,
    validator = x3_g01_power_validator("M40i"),
    reassign = reassign_x3_g01("otomoto"),
    defaults = {
        "power_hp":     360,
        "engine_cc":    2998,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
