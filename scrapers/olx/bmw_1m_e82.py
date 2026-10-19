"""BMW 1M Coupe E82 (2011–2012) (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/bmw_1m_e82.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Inherits the otomoto genuine-1M validator (manual gearbox, UR9/1LK VIN, price sanity).
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_1m_e82 import CONFIG as OTOMOTO
from olx._common import all_of, min_power_validator


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/q-1m/"
        "?search[filter_float_year:from]=2011"
        "&search[filter_float_year:to]=2012"
        "&page={page}"
    ),
    title_must_contain = ['1m', '1 m'],
    min_year = 2011,
    max_year = 2012,
    validator = all_of(OTOMOTO.validator, min_power_validator(330, '1m')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
