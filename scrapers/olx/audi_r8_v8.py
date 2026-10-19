"""Audi R8 V8 (4.2 FSI) (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/audi_r8_v8.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Text search (OLX has no R8 slug). V10 ads are excluded by title or stated capacity.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.audi_r8_v8 import CONFIG as OTOMOTO
from olx._common import engine_cc_validator


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/audi/q-r8/"
        "?"
        "&page={page}"
    ),
    title_must_contain = ['r8'],
    title_must_not_contain = ['v10', '5.2'],
    validator = engine_cc_validator(None, 4500, 'r8-v8'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
