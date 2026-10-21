"""Audi RS4 B8.5 Avant (2013–2015) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/audi_rs4_b85.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
Text search (OLX has no RS4 slug); the title keyword and year range narrow it.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import olx_url
from otomoto.audi_rs4_b85 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('audi', ['rs4-avant'], year_from=2013, year_to=2015),
    title_must_contain = ['RS4', 'RS 4'],
    min_year = 2013,
    max_year = 2015,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
