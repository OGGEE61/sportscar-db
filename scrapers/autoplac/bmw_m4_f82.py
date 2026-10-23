"""BMW M4 F82 (2014–2020) (autoplac.pl) — run directly to scrape.

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
from otomoto.bmw_m4_f82 import CONFIG_M4 as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("bmw", "m-4", year_from=2014, year_to=2020, power_from=420, power_to=510),  # up to M4 GTS
)

if __name__ == "__main__":
    run(CONFIG)
