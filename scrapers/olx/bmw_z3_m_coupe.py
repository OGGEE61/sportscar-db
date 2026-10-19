"""BMW Z3 M Coupe/Roadster (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/bmw_z3_m_coupe.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
The title must say M; power >= 300 HP drops the 2.0-2.8 Z3 cars.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_z3_m_coupe import CONFIG as OTOMOTO
from olx._common import min_power_validator


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/q-z3-m/"
        "?"
        "&page={page}"
    ),
    title_must_contain = ['z3m', 'z3 m', 'z3-m', 'm coupe', 'm roadster'],
    validator = min_power_validator(300, 'z3-m'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
