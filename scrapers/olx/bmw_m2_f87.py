"""BMW M2 F87 (2016–2021) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/bmw_m2_f87.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_m2_f87 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/m2/"
        "?search[filter_float_year:from]=2016"
        "&search[filter_float_year:to]=2021"
        "&page={page}"
    ),
    title_must_contain = ['M2'],
    min_year = 2016,
    max_year = 2021,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
