"""Mercedes E63 AMG W212 (2009–2016) (OLX) — run directly to scrape.

Same make/model/variant, specs and checks as scrapers/otomoto/mercedes_e63_w212.py, so OLX finds land on the
same model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are already
collected by the otomoto scraper.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_e63_w212 import CONFIG as OTOMOTO
from olx._common import olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['e-class'], year_from=2009, year_to=2016, power_from=521, size_from=5400),
    validator = OTOMOTO.validator,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
