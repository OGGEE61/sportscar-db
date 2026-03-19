"""Porsche 911 997 (2004–2012) — run directly to scrape."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Porsche",
    model   = "911",
    variant = "997",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-porsche-911/"
        "?search%5Bfilter_enum_model%5D%5B0%5D=911"
        "&search%5Bfilter_float_year%3Afrom%5D=2004"
        "&search%5Bfilter_float_year%3Ato%5D=2012"
        "&page={page}"
    ),
    pages = 5,
)

if __name__ == "__main__":
    run(CONFIG)
