"""Toyota GR Yaris (2020+) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/toyota_gr_yaris.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
Text search; plain Yaris ads are dropped by the title filter.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import olx_url
from otomoto.toyota_gr_yaris import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('toyota', ['yaris'], year_from=2020, power_from=250),
    title_must_contain = ['GR Yaris', 'GR-Yaris', 'GRYaris'],
    min_year = 2020,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
