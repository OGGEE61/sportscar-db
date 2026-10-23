"""Mercedes A45 AMG W176 (2016–2020) (autoplac.pl) — run directly to scrape.

Same make/model/variant and specs as the OLX scraper, so autoplac finds
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
from olx.mercedes_a45_w176 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # 350+ HP in the A-Class is the A45; the OTOMOTO validator (kept) rejects the W177 / A45 S
    list_url = autoplac_url("mercedes-benz", "klasa-a", year_from=2016, year_to=2020, power_from=350, power_to=400, cc_from=1900),
    title_must_contain = None,
    title_must_not_contain = [],
    skip_otomoto_hosted = False,
)

if __name__ == "__main__":
    run(CONFIG)
