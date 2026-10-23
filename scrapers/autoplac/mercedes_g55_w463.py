"""Mercedes G55 AMG W463 (to 2012) (autoplac.pl) — run directly to scrape.

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
from otomoto.mercedes_g55_w463 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # 450+ HP leaves out the G500 (5.5 biturbo, 388 HP) that shares the engine size range
    list_url = autoplac_url("mercedes-benz", "klasa-g", year_to=2012, power_from=450, cc_from=5300, cc_to=5600),
    title_must_contain = None,
    title_must_not_contain = [],
    max_year = 2012,
    validator = all_of(engine_cc_validator(5300, 5600, 'g55'), min_power_validator(450, 'g55')),
)

if __name__ == "__main__":
    run(CONFIG)
