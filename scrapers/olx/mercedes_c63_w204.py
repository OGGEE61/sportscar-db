"""Mercedes C63 AMG W204 (2008–2015) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/mercedes_c63_w204.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
OLX has no C63 model filter, so this is a text search; the validator drops
C180/C200 'AMG pakiet' cars when the listing states power or capacity.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_c63_w204 import CONFIG as OTOMOTO


def validate_c63(detail: dict) -> bool:
    """Reject non-AMG C-Class listings whose stated specs rule out the 6.2 V8."""
    power = detail.get("power_hp") or 0
    cc = detail.get("engine_cc") or 0
    if (power and power < 450) or (cc and cc < 6000):
        print(f"  [reject-c63] {power} KM / {cc} cm3 -- not a C63 W204.")
        return False
    return True


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/q-c63/"
        "?search[filter_float_year:from]=2008"
        "&search[filter_float_year:to]=2015"
        "&page={page}"
    ),
    title_must_contain = ['C63', 'C 63'],
    min_year = 2008,
    max_year = 2015,
    validator = validate_c63,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
