"""Audi RS5 B8/B9 (2010–2020) — run directly to scrape.

B8  = 2010–2016 (4.2 V8 FSI)
B9  = 2017–2020 (2.9 TFSI biturbo)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS5",
    variant = "B8/B9",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-audi-rs5/"
        "?search%5Bfilter_enum_model%5D%5B0%5D=rs5"
        "&search%5Bfilter_float_year%3Afrom%5D=2010"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    pages = 5,
)

if __name__ == "__main__":
    run(CONFIG)
