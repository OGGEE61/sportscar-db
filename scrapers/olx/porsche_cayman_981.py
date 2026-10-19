"""Porsche Cayman 981 (2013–2016) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/porsche_cayman_981.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
Mirrors the otomoto filters: 2013-2016 and power >= 320 HP.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.porsche_cayman_981 import CONFIG as OTOMOTO
from olx._common import min_power_validator, olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('porsche', ['cayman'], year_from=2013, year_to=2016, power_from=320),
    title_must_contain = ['cayman'],
    title_must_not_contain = ['boxster', '911', 'carrera', 'macan', 'panamera', 'cayenne', 'taycan'],
    min_year = 2013,
    max_year = 2016,
    validator = min_power_validator(320, 'cayman-981'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
