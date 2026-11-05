"""BMW M340i G20 / G21 (2019–) (OLX) — run directly to scrape.

Same make/model/variant, specs and checks as scrapers/otomoto/bmw_m340i_g20.py, so OLX finds land
on the same model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are
already collected by the otomoto scraper. OLX has no generation filter: the years and specs pick it.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_m340i_g20 import CONFIG as OTOMOTO
from olx._common import olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('bmw', ['3-as-sorozat'], year_from=2019, power_from=350, power_to=420, size_from=2900, size_to=3100),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
