"""BMW M3 E46 (2000–2006) (autoplac.pl) — run directly to scrape.

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
from otomoto.bmw_m3_e46 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("bmw", "m-3", year_from=2000, year_to=2006, power_from=330, power_to=370),  # up to M3 CSL
    min_year = 2000,
    max_year = 2006,
)

if __name__ == "__main__":
    run(CONFIG)
