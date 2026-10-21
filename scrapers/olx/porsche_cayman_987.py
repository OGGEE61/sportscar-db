"""Porsche Cayman 987 (2005–2012) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/porsche_cayman_987.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
Mirrors the otomoto filters: year <= 2012 and power >= 290 HP (drops the 2.7 base car).
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.porsche_cayman_987 import CONFIG as OTOMOTO
from olx._common import min_power_validator, olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('porsche', ['cayman'], year_to=2012, power_from=290),
    title_must_contain = ['cayman'],
    title_must_not_contain = ['boxster', '911', 'carrera', 'macan', 'panamera', 'cayenne', 'taycan'],
    max_year = 2012,
    validator = min_power_validator(290, 'cayman-987'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
