"""Audi RS Q3 F3 (2019–) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds land on the same model
in analytics. autoplac titles are generated from the model data, so only the year filters.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.audi_rsq3_f3 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("audi", "rs-q3", year_from=2019),
    title_must_not_contain = [],
    min_year = 2019,
    validator = BASE.validator,
)

if __name__ == "__main__":
    run(CONFIG)
