"""Mercedes W124 (1984–1997), 3.0 diesels and six- and eight-cylinder petrols (autoplac.pl) — run directly to scrape.

Same make/model/variant and engine rules as the otomoto scraper, so autoplac finds land on the same
model in analytics. autoplac files the car as 'w124' and as 'klasa-e'; the latter also returns the
first W210s (1995-), which its generated titles name, and the VIN rules out.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_e_w124 import CONFIG as BASE, PETROL_MIN_CC
from olx._common import all_of, year_required
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = [
        autoplac_url("mercedes-benz", "w124", year_from=1984, year_to=1997, cc_from=PETROL_MIN_CC),
        autoplac_url("mercedes-benz", "klasa-e", year_from=1984, year_to=1997, cc_from=PETROL_MIN_CC),
    ],
    title_must_not_contain = ["W210"],
    validator = all_of(BASE.validator, year_required('w124')),
)

if __name__ == "__main__":
    run(CONFIG)
