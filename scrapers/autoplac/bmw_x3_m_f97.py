"""BMW X3 M F97 (2019–2024) (autoplac.pl) — run directly to scrape.

autoplac has no separate X3 M model: X3 filtered to 440+ HP. The OLX validator
rejects M40i/M40d (also those badged as X3 M).
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx.bmw_x3_m_f97 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("bmw", "x3", year_from=2019, year_to=2024, power_from=440),
)

if __name__ == "__main__":
    run(CONFIG)
