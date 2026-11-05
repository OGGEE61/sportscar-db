"""Mercedes G-Class W460 / W461 / W463 without the W464 (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the otomoto scraper, so autoplac finds land on the same model
in analytics. autoplac titles are generated from the model data, so the years leave out the W464 (a W463 first registered in 2018 is missed) and the
specs leave out the G55, which has its own scraper.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from otomoto.mercedes_g_w463 import CONFIG as BASE
from olx._common import all_of, year_required
from autoplac._common import autoplac_url


def not_g55_specs(detail: dict) -> bool:
    cc, power = detail.get("engine_cc") or 0, detail.get("power_hp") or 0
    if 5300 <= cc <= 5600 and power >= 450:
        print("  [skip] G55: has its own scraper")
        return False
    return True


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = autoplac_url("mercedes-benz", "klasa-g", year_to=2017),
    title_must_not_contain = [],
    max_year = 2017,
    validator = all_of(BASE.validator, not_g55_specs, year_required('g_w463')),
)

if __name__ == "__main__":
    run(CONFIG)
