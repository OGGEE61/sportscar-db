"""Audi RS Q3 F3 (2019–) (OLX) — run directly to scrape.

Same make/model/variant, specs and checks as scrapers/otomoto/audi_rsq3_f3.py, so OLX finds land on the
same model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are already
collected by the otomoto scraper.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.audi_rsq3_f3 import CONFIG as OTOMOTO
from olx._common import olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('audi', ['rs-q3'], year_from=2019),
    min_year = 2019,
    validator = OTOMOTO.validator,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
