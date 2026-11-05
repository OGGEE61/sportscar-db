"""Mercedes S-Class W140 (1991–1998) (OLX) — run directly to scrape.

Same make/model/variant, specs and checks as scrapers/otomoto/mercedes_s_w140.py, so OLX finds land on the
same model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are already
collected by the otomoto scraper.
OLX has no generation filter: the years pick the W140, the VIN rules out a W126 or W220.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_s_w140 import CONFIG as OTOMOTO
from olx._common import all_of, olx_url, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['s-class'], year_from=1991, year_to=1998),
    max_year = 1998,
    validator = all_of(OTOMOTO.validator, year_required('w140')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
