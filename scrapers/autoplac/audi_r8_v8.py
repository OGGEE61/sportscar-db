"""Audi R8 V8 (4.2) (autoplac.pl) — run directly to scrape.

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
from otomoto.audi_r8_v8 import CONFIG as BASE
from olx._common import engine_cc_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Told apart from the V10 by engine size: 4.2 here, 5.2 in the V10 scraper
    list_url = autoplac_url("audi", "r8", cc_to=4500),
    title_must_contain = None,
    validator = engine_cc_validator(None, 4500, 'r8-v8'),
)

if __name__ == "__main__":
    run(CONFIG)
