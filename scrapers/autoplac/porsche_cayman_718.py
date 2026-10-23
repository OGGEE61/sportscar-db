"""Porsche 718 Cayman (2016–) (autoplac.pl) — run directly to scrape.

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
from otomoto.porsche_cayman_718 import CONFIG as BASE
from olx._common import min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # '718 Cayman' holds the 718s; plain 'Cayman' from 2017 is a 718 too (the 981 ended in 2016)
    list_url = [
        autoplac_url("porsche", "718-cayman", power_from=345),
        autoplac_url("porsche", "cayman", year_from=2017, power_from=345),
    ],
    min_year = 2016,
    validator = min_power_validator(345, '718-cayman'),
)

if __name__ == "__main__":
    run(CONFIG)
