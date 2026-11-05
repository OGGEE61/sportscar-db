"""Mercedes E63 AMG W212 (2009–2016) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds land on the same model
in analytics. autoplac titles are generated from the model data, so year, power and engine size filter.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_e63_w212 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = [
        autoplac_url("mercedes-benz", "klasa-e", year_from=2009, year_to=2016, power_from=521, cc_from=5400, cc_to=6300),
        autoplac_url("mercedes-benz", "e", year_from=2009, year_to=2016, power_from=521, cc_from=5400, cc_to=6300),
    ],
    title_must_not_contain = [],
    min_year = 2009,
    max_year = 2016,
    validator = all_of(BASE.validator, engine_cc_validator(5400, 6300, 'e63'), min_power_validator(521, 'e63')),
)

if __name__ == "__main__":
    run(CONFIG)
