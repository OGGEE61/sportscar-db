"""Mercedes S55 AMG W220 (to 2005) (autoplac.pl) — run directly to scrape.

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
from otomoto.mercedes_s55_w220 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Sellers file the S-Class under both 'Klasa S' and 'S'. Up to 5.5 litres leaves out the
    # S600 (5.5 V12 biturbo, 5513 cm3); 450+ HP leaves out the S500 and up to 560 HP the S65 (612),
    # which sellers sometimes list with the S55's engine size
    list_url = [
        autoplac_url("mercedes-benz", "klasa-s", year_to=2005, power_from=450, cc_from=5300, cc_to=5500, power_to=560),
        autoplac_url("mercedes-benz", "s", year_to=2005, power_from=450, cc_from=5300, cc_to=5500, power_to=560),
    ],
    title_must_contain = None,
    title_must_not_contain = [],
    max_year = 2005,
    validator = all_of(engine_cc_validator(5300, 5500, 's55'), min_power_validator(450, 's55')),
)

if __name__ == "__main__":
    run(CONFIG)
