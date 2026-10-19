"""Mercedes SL55 AMG R230 (up to 2008) (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/mercedes_sl55_r230.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
SL 550 contains 'sl55' and ML 55 matches '55 amg', so the keyword list is stricter than otomoto's.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import all_of, year_required
from otomoto.mercedes_sl55_r230 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/q-sl55/"
        "?search[filter_float_year:to]=2008"
        "&page={page}"
    ),
    title_must_contain = ['sl55', 'sl 55', 'sl-55'],
    title_must_not_contain = OTOMOTO.title_must_not_contain + ['sl550', 'sl 550', 'ml55', 'ml 55'],
    max_year = 2008,
    validator = year_required('sl55'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
