"""Mercedes CL55 AMG C215 (up to 2006) (OLX) — run directly to scrape.

Same make/model/variant, specs and title filters as scrapers/otomoto/mercedes_cl55_c215.py, so
OLX finds land on the same model in analytics. Only OLX's own ads are scraped:
the cross-posted otomoto ads are already collected by the otomoto scraper.
Text search; the otomoto title filters drop CL500/600/63/65.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import olx_url
from otomoto.mercedes_cl55_c215 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('mercedes-benz', ['cl-class'], year_to=2006, size_from=5300, size_to=5600),
    max_year = 2006,
    # 'ml 55 amg' / 'c55 amg' also match the generic '55 amg' keyword
    title_must_contain = ['cl55', 'cl 55', 'cl-55'],
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
