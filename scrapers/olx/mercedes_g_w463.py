"""Mercedes G-Class W460 / W461 / W463 without the W464 (OLX) — run directly to scrape.

Same make/model/variant, specs and checks as scrapers/otomoto/mercedes_g_w463.py, so OLX finds land on the
same model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are already
collected by the otomoto scraper.
OLX has no generation filter, and the W464 from 2018 has the same model and VIN code, so only cars
up to 2017 are taken: a real W463 first registered in 2018 is missed here.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_g_w463 import CONFIG as OTOMOTO
from olx._common import all_of, olx_url, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['g-class'], year_to=2017),
    max_year = 2017,
    validator = all_of(OTOMOTO.validator, year_required('g_w463')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
