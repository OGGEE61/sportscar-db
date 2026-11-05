"""BMW M5 F10 (2011–2017) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/bmw_m5_f10.py, so OLX finds land on the same
model in analytics. Only OLX's own ads are scraped: the cross-posted otomoto ads are already
collected by the otomoto scraper. Power >= 540 HP leaves out regular 5 Series filed as M5.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_m5_f10 import CONFIG as OTOMOTO
from olx._common import all_of, min_power_validator, olx_url, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('bmw', ['m5'], year_from=2011, year_to=2017),
    title_must_contain = ['m5'],
    min_year = 2011,
    max_year = 2017,
    validator = all_of(OTOMOTO.validator, min_power_validator(540, 'm5-f10'), year_required('m5-f10')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
