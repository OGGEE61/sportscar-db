"""Audi RS3 8V facelift (2017–2020) — run directly to scrape."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Audi",
    model   = "RS3",
    variant = "8V",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-audi-rs3/"
        "?search%5Bfilter_enum_model%5D%5B0%5D=rs3"
        "&search%5Bfilter_float_year%3Afrom%5D=2017"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    pages = 5,
)

if __name__ == "__main__":
    run(CONFIG)
