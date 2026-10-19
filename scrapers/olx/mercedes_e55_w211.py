"""Mercedes E55 AMG W211 (2003–2006) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_e55_w211.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Power >= 460 HP like the otomoto filter.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_e55_w211 import CONFIG as OTOMOTO
from olx._common import min_power_validator


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/q-e55/"
        "?search[filter_float_year:from]=2003"
        "&search[filter_float_year:to]=2006"
        "&page={page}"
    ),
    min_year = 2003,
    max_year = 2006,
    validator = min_power_validator(460, 'e55'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
