"""BMW M340i G20 / G21 (2019–) — run directly to scrape.

3.0L B58 twin-power turbo, 374-387 HP, xDrive, 8-speed automatic, sedan or Touring. Engine size,
petrol and 350-420 HP leave out the M340d, the 330i and the Alpina B3.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run


def is_m340i(detail: dict) -> bool:
    return "diesel" not in (detail.get("fuel_type") or "").lower()


CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "Seria 3",
    variant = "M340i G20",
    source  = "otomoto",
    model_id = "m340i_g20",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/seria-3"
        "?search%5Bfilter_enum_generation%5D=gen-g20-2019"
        "&search%5Bfilter_enum_fuel_type%5D=petrol"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=2900"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=3100"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=350"
        "&search%5Bfilter_float_engine_power%3Ato%5D=420"
        "&page={page}"
    ),
    min_year = 2019,
    validator = is_m340i,
    defaults = {
        "power_hp":     374,
        "engine_cc":    2998,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "AWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
