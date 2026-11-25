"""Mercedes-Benz W124 (1984–1997): 3.0 diesels and petrols from the 320 up — run directly to scrape.

Wanted: the 3.0 diesel (300D / E300 Diesel, also Turbodiesel) and petrols from the 3.2 six up
(320E / E320, E36 AMG, 400E / E420, 500E / E500, E60 AMG). Left out: the smaller petrols (200E-230E,
E200, E220, 260E, 280E, 300E) and the 2.0 and 2.5 diesels.

Otomoto files the car twice: as its own model "W124 (1984-1993)" and, from the 1993 facelift, as
an E-Class generation. Each gets a diesel search (2.9-3.1 l) and a petrol search (3.1 l up).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_other_mercedes_chassis

DIESEL_CC = (2900, 3100)   # OM603 / OM606: 2996-2999 cm3
PETROL_MIN_CC = 3100       # the 320E / E320 is 3199 cm3; the 300E (2960-2962) is left out


def is_wanted_w124(detail: dict) -> bool:
    """A W124 by VIN (when it has one) with a wanted engine. An unknown engine size passes."""
    if is_other_mercedes_chassis(detail.get("vin"), "124"):
        return False
    cc = detail.get("engine_cc") or 0
    if not cc:
        return True
    if "diesel" in (detail.get("fuel_type") or "").lower():
        if not DIESEL_CC[0] <= cc <= DIESEL_CC[1]:
            print(f"  [reject-w124] diesel {cc} cm3: only the 3.0 is wanted.")
            return False
    elif cc < PETROL_MIN_CC:
        print(f"  [reject-w124] petrol {cc} cm3: only the 320 and bigger are wanted.")
        return False
    return True


_FILED_AS = ("w124-1984-1993", "e-klasa?search%5Bfilter_enum_generation%5D=gen-w124-1993-1997")
_ENGINES = (
    "search%5Bfilter_enum_fuel_type%5D=diesel"
    f"&search%5Bfilter_float_engine_capacity%3Afrom%5D={DIESEL_CC[0]}"
    f"&search%5Bfilter_float_engine_capacity%3Ato%5D={DIESEL_CC[1]}",
    "search%5Bfilter_enum_fuel_type%5D=petrol"
    f"&search%5Bfilter_float_engine_capacity%3Afrom%5D={PETROL_MIN_CC}",
)

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa E",
    variant = "W124",
    source  = "otomoto",
    model_id = "e_w124",
    list_url = [
        f"https://www.otomoto.pl/osobowe/mercedes-benz/{filed}{'&' if '?' in filed else '?'}{engine}&page={{page}}"
        for filed in _FILED_AS for engine in _ENGINES
    ],
    min_year = 1984,
    max_year = 1997,
    validator = is_wanted_w124,
)

if __name__ == "__main__":
    run(CONFIG)
