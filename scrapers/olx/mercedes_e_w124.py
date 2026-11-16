"""Mercedes W124 (1984–1997), 3.0 diesels and six- and eight-cylinder petrols (OLX) — run directly to scrape.

Same make/model/variant and engine rules as scrapers/otomoto/mercedes_e_w124.py, so OLX finds land on the
same model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are already
collected by the otomoto scraper.
OLX files the car as 'w124' and as 'e-class'; it has no fuel filter, so the search takes every engine
from 2.5 l and the validator drops the diesels that are not 3.0. The years also cover the first
W210s (1995-): the VIN and the title rule those out.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_e_w124 import CONFIG as OTOMOTO, PETROL_MIN_CC
from olx._common import all_of, olx_url, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['w124', 'e-class'], year_from=1984, year_to=1997, size_from=PETROL_MIN_CC),
    title_must_not_contain = ["W210", "W 210"],
    validator = all_of(OTOMOTO.validator, year_required('w124')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
