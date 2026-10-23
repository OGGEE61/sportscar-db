"""Audi RS4 B9 Avant (2017–2019) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds
land on the same model in analytics.
autoplac has few RS4s; the model page holds them all.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.audi_rs4_b9 import CONFIG as BASE
from olx._common import engine_cc_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("audi", "rs4", year_from=2017, year_to=2019),
    validator = engine_cc_validator(2800, 3000, 'rs4-b9'),  # 2.9 V6; the B8 is a 4.2 V8
)

if __name__ == "__main__":
    run(CONFIG)
