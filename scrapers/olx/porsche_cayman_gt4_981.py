"""Porsche Cayman GT4 981 (2015–2016) (OLX) — run directly to scrape.

Same make/model/variant and specs as scrapers/otomoto/porsche_cayman_gt4_981.py, so OLX finds
land on the same model in analytics. Only OLX's own ads are scraped: the
cross-posted otomoto ads are already collected by the otomoto scraper.
Text search; the GT4 title keyword is required.
"""
import dataclasses
import os
import sys
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import run
from olx._common import olx_url
from otomoto.porsche_cayman_gt4_981 import CONFIG as OTOMOTO


CONFIG = dataclasses.replace(
    OTOMOTO,
    source   = "olx",
    list_url = olx_url('porsche', ['cayman'], year_from=2015, year_to=2016, power_from=370),
    title_must_contain = ['GT4'],
    title_must_not_contain = ['911', 'carrera', 'macan', 'panamera', 'cayenne', 'taycan'],
    min_year = 2015,
    max_year = 2016,
    skip_otomoto_hosted = True,
)

if __name__ == "__main__":
    run(CONFIG)
