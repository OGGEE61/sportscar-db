"""Mercedes S55 AMG W220 (up to 2005) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_s55_w220.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Text search; the otomoto title filters drop other AMG 55s and S500/600/63/65.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_s55_w220 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/q-s55/"
        "?search[filter_float_year:to]=2005"
        "&page={page}"
    ),
    max_year = 2005,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
