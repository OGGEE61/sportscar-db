"""BMW M5 F10 (2011–2017) — run directly to scrape.

4.4L S63 twin-turbo V8, 560-600 HP, RWD, 7-speed DCT (a few 6-speed manuals).
540+ HP leaves out regular 5 Series filed as M5; the VIN rules out an early F90 from 2017.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run


def not_f90(detail: dict) -> bool:
    return not (detail.get("vin") or "").upper().startswith(("WBSJF", "WBS83"))


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "M5",
    variant = "F10 M5",
    source  = "otomoto",
    model_id = "m5_f10",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m5"
        "?search%5Bfilter_float_year%3Afrom%5D=2011"
        "&search%5Bfilter_float_year%3Ato%5D=2017"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=540"
        "&page={page}"
    ),
    validator = not_f90,
    defaults = {
        "power_hp":     560,
        "engine_cc":    4395,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Sedan",
    },
)

if __name__ == "__main__":
    run(CONFIG)
