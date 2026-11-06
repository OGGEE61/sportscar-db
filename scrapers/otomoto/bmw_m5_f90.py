"""BMW M5 F90 (2018–2024) — run directly to scrape.

4.4L S63 twin-turbo V8, 600-635 HP, M xDrive AWD, 8-speed automatic. Up to 700 HP leaves out the
727 HP hybrid G90. The first cars are from 2017, when the F10 was still on sale, so a 2017 car
only counts here with an F90 VIN.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

F90_VIN = ("WBSJF", "WBS83", "WBS81", "WBSGV")


def is_f90(detail: dict) -> bool:
    vin = (detail.get("vin") or "").upper()
    if vin.startswith(("WBSFV", "WBSFK")):
        return False
    if not vin and detail.get("before_reveal"):
        return True     # a 2017 car is decided once its VIN is revealed
    return (detail.get("year") or 0) >= 2018 or vin.startswith(F90_VIN)


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "M5",
    variant = "F90 M5",
    source  = "otomoto",
    model_id = "m5_f90",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m5"
        "?search%5Bfilter_float_year%3Afrom%5D=2017"
        "&search%5Bfilter_float_year%3Ato%5D=2024"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=590"
        "&search%5Bfilter_float_engine_power%3Ato%5D=700"
        "&page={page}"
    ),
    validator = is_f90,
    defaults = {
        "engine_cc":    4395,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
        "body_type":    "Sedan",
    },
)

if __name__ == "__main__":
    run(CONFIG)
