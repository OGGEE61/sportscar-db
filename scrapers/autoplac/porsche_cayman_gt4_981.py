"""Porsche Cayman GT4 981 (2015–2016) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds
land on the same model in analytics.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.porsche_cayman_gt4_981 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # The 3.8 litre engine is the GT4's; the card title rarely says GT4 so it is not required
    list_url = [
        autoplac_url("porsche", "981-cayman", year_from=2015, year_to=2016, power_from=370, cc_from=3700),
        autoplac_url("porsche", "cayman", year_from=2015, year_to=2016, power_from=370, cc_from=3700),
    ],
    title_must_contain = None,
    min_year = 2015,
    max_year = 2016,
    validator = all_of(engine_cc_validator(3700, 3900, 'cayman-gt4'), min_power_validator(370, 'cayman-gt4')),
)

if __name__ == "__main__":
    run(CONFIG)
