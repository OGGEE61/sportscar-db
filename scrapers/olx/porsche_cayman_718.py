"""Porsche 718 Cayman (2016+) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/porsche_cayman_718.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
OLX has no 718 model slug, so this is a text search. Power >= 345 HP like otomoto.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.porsche_cayman_718 import CONFIG as OTOMOTO
from olx._common import min_power_validator, olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('porsche', ['718-cayman'], power_from=345),
    title_must_contain = ['cayman'],
    title_must_not_contain = ['boxster', '911', 'carrera', 'macan', 'panamera', 'cayenne', 'taycan'],
    min_year = 2016,
    validator = min_power_validator(345, '718-cayman'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
