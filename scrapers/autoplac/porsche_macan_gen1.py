"""Porsche Macan Gen 1 GTS / Turbo (to 2018) (autoplac.pl) — run directly to scrape.

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
from otomoto.porsche_macan_gen1 import CONFIG as BASE
from olx._common import all_of, min_power_validator, year_required
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # 355+ HP is the GTS (360) and the Turbo (400-440); the S stays below. autoplac titles
    # do not say GTS / Turbo ("Macan I 3.0"), so the power filter does that job.
    list_url = autoplac_url("porsche", "macan", year_to=2018, power_from=355),
    title_must_contain = None,
    title_must_not_contain = ["diesel"],
    max_year = 2018,
    validator = all_of(min_power_validator(355, 'macan'), year_required('macan')),
)

if __name__ == "__main__":
    run(CONFIG)
