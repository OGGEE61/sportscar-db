"""Audi RS4 B8 / B8.5 (2012–2015) — run directly to scrape."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS4",
    variant = "B8",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-audi-rs4/"
        "?search%5Bfilter_enum_model%5D%5B0%5D=rs4"
        "&search%5Bfilter_float_year%3Afrom%5D=2012"
        "&search%5Bfilter_float_year%3Ato%5D=2015"
        "&page={page}"
    ),
    pages = 5,
)

if __name__ == "__main__":
    run(CONFIG)
