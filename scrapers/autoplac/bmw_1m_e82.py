"""BMW 1M Coupe E82 (2011–2012) (autoplac.pl) — run directly to scrape.

Sellers file the 1M under both 'Seria 1' and 'M 1'; both are searched. The otomoto
validator checks the 1M VIN pattern, manual gearbox and price.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_1m_e82 import CONFIG as BASE
from olx._common import all_of, min_power_validator, year_required
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = [
        autoplac_url("bmw", "seria-1", year_from=2011, year_to=2012, power_from=330),
        autoplac_url("bmw", "m-1", year_from=2011, year_to=2012),
    ],
    min_year = 2011,
    max_year = 2012,
    validator = all_of(BASE.validator, min_power_validator(330, '1m'), year_required('1m')),
)

if __name__ == "__main__":
    run(CONFIG)
