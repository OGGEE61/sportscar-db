"""BMW M340i G20 / G21 (2019–) — run directly to scrape.

3.0L B58 twin-power turbo, 374-387 HP, xDrive, 8-speed automatic, sedan or Touring. Engine size,
petrol and 350-420 HP leave out the M340d, the 330i and the Alpina B3. Still sold new, so dealer
stock is left out the same way as for the M2 G87.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_dealer_new


def used_m340i(detail: dict) -> bool:
    if "diesel" in (detail.get("fuel_type") or "").lower():
        return False
    return not is_dealer_new(detail.get("year"), detail.get("mileage_km"),
                             detail.get("first_registration_date"))


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
    validator = used_m340i,
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
