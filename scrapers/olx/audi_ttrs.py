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
from olx._common import all_of, min_power_validator, olx_url, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('audi', ['tt-rs', 'tt-rs-roadster'], year_from=2009),
    title_must_contain = ['tt rs', 'ttrs', 'tt-rs'],
    min_year = 2009,
    validator = all_of(min_power_validator(330, 'tt-rs'), year_required('tt-rs')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
