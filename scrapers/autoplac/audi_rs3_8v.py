"""Audi RS3 8V (2017–2020) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds
land on the same model in analytics.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.audi_rs3_8v import CONFIG as BASE
from olx._common import min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("audi", "rs3", year_from=2017, year_to=2020),
    min_year = 2017,
    max_year = 2020,
    validator = min_power_validator(350, 'rs3'),
)

if __name__ == "__main__":
    run(CONFIG)
