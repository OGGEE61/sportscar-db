"""Mercedes S-Class W140 (1991–1998) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds land on the same model
in analytics. autoplac titles are generated from the model data, so the years pick the W140 and the VIN rules out a W126 or W220.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_s_w140 import CONFIG as BASE
from olx._common import all_of, year_required
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = [
        autoplac_url("mercedes-benz", "klasa-s", year_from=1991, year_to=1998),
        autoplac_url("mercedes-benz", "s", year_from=1991, year_to=1998),
    ],
    title_must_not_contain = [],
    min_year = 1991,
    max_year = 1998,
    validator = all_of(BASE.validator, year_required('w140')),
)

if __name__ == "__main__":
    run(CONFIG)
