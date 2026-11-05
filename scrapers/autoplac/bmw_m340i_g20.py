"""BMW M340i G20 / G21 (2019–) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds land on the same model
in analytics. autoplac has no fuel filter here: the validator rules out the M340d.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.bmw_m340i_g20 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("bmw", "seria-3", year_from=2019, power_from=350, power_to=420, cc_from=2900, cc_to=3100),
)

if __name__ == "__main__":
    run(CONFIG)
