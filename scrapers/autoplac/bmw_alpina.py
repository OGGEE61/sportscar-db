"""BMW Alpina (autoplac.pl) — run directly to scrape.

Full-text search: some Alpinas are filed under the Alpina brand, others under BMW
with 'Alpina' in the title. The OLX validator keeps only genuine WAP VINs.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx.bmw_alpina import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url(query="alpina"),
)

if __name__ == "__main__":
    run(CONFIG)
