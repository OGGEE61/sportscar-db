"""Mercedes G55 AMG W463 (up to 2012) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_g55_w463.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Text search; the otomoto title filters drop G500/G63/G65 and other 55s.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_g55_w463 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/q-g55/"
        "?search[filter_float_year:to]=2012"
        "&page={page}"
    ),
    max_year = 2012,
    # g550 contains 'g55'; c55/ml55 match the generic '55 amg' keyword
    title_must_not_contain = OTOMOTO.title_must_not_contain + ['g550', 'g 550', 'c55', 'c 55', 'ml55', 'ml 55', 'e55', 'e 55', 'cl55', 'cl 55'],
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
