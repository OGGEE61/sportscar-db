"""BMW X3 M F97 (2019–2024) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the OLX scraper, so autoplac finds land on the
same model in analytics. Shares its searches with the X3 M40i scraper; the VIN
decides which of the two a car is (see _x3_g01.py), so an M40i badged as X3 M is
saved as an M40i, not rejected. Cars without a VIN go through the OLX validator.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx.bmw_x3_m_f97 import CONFIG as BASE
from autoplac._x3_g01 import X3_G01_URLS, reassign_x3_g01


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    list_url = X3_G01_URLS,
    # The OLX config skips "M40i" titles before the detail page; here the VIN decides
    title_must_not_contain = ["M40d", "M40 d", "diesel"],
    reassign = reassign_x3_g01,
)

if __name__ == "__main__":
    run(CONFIG)
