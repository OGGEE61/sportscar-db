"""Mercedes CLK 63 AMG W209 (2006–2009) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds
land on the same model in analytics.
autoplac titles are generated from the model data ("Klasa C W204 6.2"), so the card-title
keyword checks of the other markets are off; year, power and engine size filter instead.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_clk63_w209 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # 6.0+ litres leaves out the CLK 55 (5.4)
    list_url = autoplac_url("mercedes-benz", "clk", year_from=2006, year_to=2009, power_from=470, cc_from=6000),
    title_must_contain = None,
    min_year = 2006,
    max_year = 2009,
    validator = all_of(engine_cc_validator(6000, None, 'clk63'), min_power_validator(470, 'clk63')),
)

if __name__ == "__main__":
    run(CONFIG)
