"""BMW 135i E82/E88 (2007–2013) (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/bmw_135i_e82.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Power >= 300 HP like the otomoto filter.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_135i_e82 import CONFIG as OTOMOTO
from olx._common import all_of, min_power_validator, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/q-135i/"
        "?search[filter_float_year:from]=2007"
        "&search[filter_float_year:to]=2013"
        "&page={page}"
    ),
    title_must_contain = ['135i', '135 i'],
    # M135i is the F20 generation (title also contains '135i')
    title_must_not_contain = OTOMOTO.title_must_not_contain + ['m135i', 'm 135i'],
    min_year = 2007,
    max_year = 2013,
    validator = all_of(min_power_validator(300, '135i'), year_required('135i')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
