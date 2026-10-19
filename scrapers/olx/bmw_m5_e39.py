"""BMW M5 E39 (1998–2003) (OLX) — run directly to scrape.

Same make/model/variant, specs and validators as scrapers/otomoto/bmw_m5_e39.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Year range and power >= 390 HP keep out later M5 generations and plain 5-series.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_m5_e39 import CONFIG as OTOMOTO
from olx._common import all_of, min_power_validator, olx_url, year_required


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('bmw', ['m5'], year_from=1998, year_to=2003),
    title_must_contain = ['m5'],
    min_year = 1998,
    max_year = 2003,
    validator = all_of(min_power_validator(390, 'm5-e39'), year_required('m5-e39')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
