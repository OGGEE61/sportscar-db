"""BMW Alpina (OLX) — run directly to scrape.

Hits OLX's BMW Alpina query. Filters out massive luxury barges (B7, XB7, XD7).
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Alpina",
    model   = "BMW",
    variant = "Alpina",
    source  = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-bmw-alpina/"
        "?page={page}"
    ),
    title_must_not_contain = ["B7", "XB7", "XD7"],
    defaults = {
        "make": "Alpina",
    },
)

if __name__ == "__main__":
    run(CONFIG)
