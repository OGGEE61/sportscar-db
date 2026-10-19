"""Audi TT RS (2009+) (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/audi_ttrs.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Power >= 330 HP drops TT/TTS cars sold with 'RS look' packages.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.audi_ttrs import CONFIG as OTOMOTO
from olx._common import min_power_validator


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/audi/q-tt-rs/"
        "?search[filter_float_year:from]=2009"
        "&page={page}"
    ),
    title_must_contain = ['tt rs', 'ttrs', 'tt-rs'],
    min_year = 2009,
    validator = min_power_validator(330, 'tt-rs'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
