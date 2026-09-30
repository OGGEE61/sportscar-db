"""BMW Alpina — run directly to scrape.

Hits otomoto's Alpina category. Filters out massive luxury barges (B7, XB7, XD7).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Alpina",
    model   = "BMW",
    variant = "Alpina",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/alpina"
        "?page={page}"
    ),
    title_must_not_contain = ["B7", "XB7", "XD7"],
    pages = 3,
    defaults = {
        "make": "Alpina",
    },
)

if __name__ == "__main__":
    run(CONFIG)
