"""Mercedes A45 AMG W176 (2016–2020) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_a45_w176.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Inherits the otomoto A45 validator and title filters.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_a45_w176 import CONFIG as OTOMOTO
from olx._common import all_of, min_power_validator, olx_url


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['a-class'], year_from=2016, year_to=2020, power_from=350, power_to=400),
    min_year = 2016,
    max_year = 2020,
    # card-title filter: the otomoto one also accepts any 'klasa a' / any GLA
    title_must_contain = ['a45', 'a 45', 'a-45', 'amg 45', '45 amg', '45amg'],
    validator = all_of(OTOMOTO.validator, min_power_validator(350, 'a45')),
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
