"""Mercedes C63 AMG W204 (2008–2015) (autoplac.pl) — run directly to scrape.

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
from olx.mercedes_c63_w204 import CONFIG as BASE
from autoplac._common import autoplac_url


CONFIG = dataclasses.replace(
    BASE,
    source   = "autoplac",
    # Sellers file the C-Class under both 'Klasa C' and 'C'. 6.0+ litres leaves out the
    # W205 C63 (4.0); the OLX validator keeps the power / engine size check.
    list_url = [
        autoplac_url("mercedes-benz", "klasa-c", year_from=2008, year_to=2015, power_from=450, cc_from=6000),
        autoplac_url("mercedes-benz", "c", year_from=2008, year_to=2015, power_from=450, cc_from=6000),
    ],
    title_must_contain = None,
    skip_otomoto_hosted = False,
)

if __name__ == "__main__":
    run(CONFIG)
