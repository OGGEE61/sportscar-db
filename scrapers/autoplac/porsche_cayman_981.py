"""Porsche Cayman 981 (2013–2016) (autoplac.pl) — run directly to scrape.

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
from otomoto.porsche_cayman_981 import CONFIG as BASE
from olx._common import all_of, engine_cc_validator, min_power_validator
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Sellers file it under '981 Cayman' and plain 'Cayman'. 3.4 litres and 320+ HP is the S / GTS;
    # the 3.8 GT4 has its own scraper and the 718 is a 2.5 turbo.
    list_url = [
        autoplac_url("porsche", "981-cayman", year_from=2013, year_to=2016, power_from=320, cc_from=3300, cc_to=3600),
        autoplac_url("porsche", "cayman", year_from=2013, year_to=2016, power_from=320, cc_from=3300, cc_to=3600),
    ],
    min_year = 2013,
    max_year = 2016,
    validator = all_of(engine_cc_validator(3300, 3600, 'cayman-981'), min_power_validator(320, 'cayman-981')),
)

if __name__ == "__main__":
    run(CONFIG)
