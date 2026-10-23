"""Audi TT RS (8J / 8S, 2009–) (autoplac.pl) — run directly to scrape.

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
from otomoto.audi_ttrs import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # autoplac has no TT RS model: it is a TT. 2.5 litres and 330+ HP leave out the other TTs.
    list_url = autoplac_url("audi", "tt", year_from=2009, power_from=330, cc_from=2400, cc_to=2600),
    title_must_contain = None,
    min_year = 2009,
    validator = all_of(engine_cc_validator(2400, 2600, 'tt-rs'), min_power_validator(330, 'tt-rs')),
)

if __name__ == "__main__":
    run(CONFIG)
