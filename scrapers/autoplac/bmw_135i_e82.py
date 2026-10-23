"""BMW 135i E82/E88 (2007–2013) (autoplac.pl) — run directly to scrape.

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
from otomoto.bmw_135i_e82 import CONFIG as BASE
from olx._common import all_of, min_power_validator, year_required
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # 300-335 HP leaves out the 1M (340 HP)
    list_url = autoplac_url("bmw", "seria-1", year_from=2007, year_to=2013, power_from=300, power_to=335),
    # M135i is the F20 generation (title also contains '135i')
    title_must_not_contain = BASE.title_must_not_contain + ['m135i', 'm 135i'],
    min_year = 2007,
    max_year = 2013,
    validator = all_of(min_power_validator(300, '135i'), year_required('135i')),
)

if __name__ == "__main__":
    run(CONFIG)
