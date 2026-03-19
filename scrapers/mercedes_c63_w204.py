"""Mercedes-Benz C63 AMG W204 (2008–2015) — run directly to scrape.

OLX has no C63-specific model filter, so we scrape the full Mercedes-Benz
brand page with year filter and skip any card whose title doesn't contain "C63".
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "C63 AMG",
    variant = "W204",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/mercedes-benz/"
        "?search%5Bfilter_float_year%3Afrom%5D=2008"
        "&search%5Bfilter_float_year%3Ato%5D=2015"
        "&page={page}"
    ),
    title_must_contain = "C63",
    pages = 5,
)

if __name__ == "__main__":
    run(CONFIG)
