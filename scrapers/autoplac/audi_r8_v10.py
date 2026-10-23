"""Audi R8 V10 (5.2) (autoplac.pl) — run directly to scrape.

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
from otomoto.audi_r8_v10 import CONFIG as BASE
from olx._common import engine_cc_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Told apart from the V8 by engine size: 5.2 here, 4.2 in the V8 scraper
    list_url = autoplac_url("audi", "r8", cc_from=4500),
    title_must_contain = None,
    validator = engine_cc_validator(4500, None, 'r8-v10'),
)

if __name__ == "__main__":
    run(CONFIG)
