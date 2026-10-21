"""Honda S2000 (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/honda_s2000.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
Text search on the title keyword.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import olx_url
from otomoto.honda_s2000 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('honda', ['s-2000']),
    title_must_contain = ['s2000', 's 2000'],
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
