"""Mercedes CLS 55 AMG C219 (2004–2006) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_cls55_c219.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Power >= 460 HP like the otomoto filter.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_cls55_c219 import CONFIG as OTOMOTO
from olx._common import min_power_validator, olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['cls-class'], year_from=2004, year_to=2006, power_from=460),
    min_year = 2004,
    max_year = 2006,
    validator = min_power_validator(460, 'cls55'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
