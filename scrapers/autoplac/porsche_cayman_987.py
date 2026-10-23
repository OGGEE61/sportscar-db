"""Porsche Cayman 987 (to 2012) (autoplac.pl) — run directly to scrape.

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
from otomoto.porsche_cayman_987 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Sellers file it under '987 Cayman' and plain 'Cayman'. 3.4 litres and 290+ HP is the S / R / GTS.
    list_url = [
        autoplac_url("porsche", "987-cayman", year_to=2012, power_from=290, cc_from=3300, cc_to=3600),
        autoplac_url("porsche", "cayman", year_to=2012, power_from=290, cc_from=3300, cc_to=3600),
    ],
    max_year = 2012,
    validator = all_of(engine_cc_validator(3300, 3600, 'cayman-987'), min_power_validator(290, 'cayman-987')),
)

if __name__ == "__main__":
    run(CONFIG)
