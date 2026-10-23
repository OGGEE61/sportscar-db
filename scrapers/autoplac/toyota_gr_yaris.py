"""Toyota GR Yaris (2020–) (autoplac.pl) — run directly to scrape.

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
from otomoto.toyota_gr_yaris import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Sellers file it under 'GR Yaris' and plain 'Yaris' (a 1.6 turbo with 250+ HP is a GR Yaris)
    list_url = [
        autoplac_url("toyota", "gr-yaris", year_from=2020, power_from=250),
        autoplac_url("toyota", "yaris", year_from=2020, power_from=250, cc_from=1500, cc_to=1700),
    ],
    title_must_contain = None,
    min_year = 2020,
    validator = all_of(engine_cc_validator(1500, 1700, 'gr-yaris'), min_power_validator(250, 'gr-yaris')),
)

if __name__ == "__main__":
    run(CONFIG)
