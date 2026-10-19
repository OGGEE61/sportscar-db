"""Mercedes CLK 63 AMG W209 (2006–2009) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_clk63_w209.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Power >= 470 HP like the otomoto filter.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_clk63_w209 import CONFIG as OTOMOTO
from olx._common import min_power_validator


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/q-clk63/"
        "?search[filter_float_year:from]=2006"
        "&search[filter_float_year:to]=2009"
        "&page={page}"
    ),
    min_year = 2006,
    max_year = 2009,
    validator = min_power_validator(470, 'clk63'),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
