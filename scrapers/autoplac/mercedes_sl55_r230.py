"""Mercedes SL55 AMG R230 (to 2008) (autoplac.pl) — run directly to scrape.

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
from otomoto.mercedes_sl55_r230 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator, year_required
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Up to 5.5 litres leaves out the SL600 (5513 cm3 V12) and the SL63 (6.2)
    list_url = autoplac_url("mercedes-benz", "sl", year_to=2008, power_from=450, cc_from=5300, cc_to=5500),
    title_must_contain = None,
    title_must_not_contain = [],
    max_year = 2008,
    validator = all_of(engine_cc_validator(5300, 5500, 'sl55'), min_power_validator(450, 'sl55'), year_required('sl55')),
)

if __name__ == "__main__":
    run(CONFIG)
