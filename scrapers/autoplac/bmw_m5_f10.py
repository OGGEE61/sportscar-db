"""BMW M5 F10 (2011–2017) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds land on the same model
in analytics.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_m5_f10 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("bmw", "m-5", year_from=2011, year_to=2017, power_from=540),
    min_year = 2011,
    max_year = 2017,
)

if __name__ == "__main__":
    run(CONFIG)
