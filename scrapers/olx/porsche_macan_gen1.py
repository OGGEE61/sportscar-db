"""Porsche Macan Gen 1 GTS / Turbo (up to 2018) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/porsche_macan_gen1.py,
so OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Power >= 350 HP like the otomoto filter (drops the 2.0 / diesel / base S cars).
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import all_of, min_power_validator, olx_url, year_required
from otomoto.porsche_macan_gen1 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('porsche', ['macan'], year_to=2018, power_from=350),
    max_year = 2018,
    validator = all_of(min_power_validator(350, 'macan'), year_required('macan')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
