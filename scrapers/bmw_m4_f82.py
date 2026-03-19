"""BMW M4 F82 / M3 F80 (2014–2020) — run directly to scrape.

Note: F80 = M3 sedan/touring, F82 = M4 coupe, F83 = M4 cabrio.
Both share the S55 engine and the same OLX generation. This scraper
covers all of them via the 'm4' and 'm3' model filters combined.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG_M4 = ScraperConfig(
    make    = "BMW",
    model   = "M4",
    variant = "F82",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/"
        "?search%5Bfilter_enum_model%5D%5B0%5D=m4"
        "&search%5Bfilter_float_year%3Afrom%5D=2014"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    pages = 5,
)

CONFIG_M3 = ScraperConfig(
    make    = "BMW",
    model   = "M3",
    variant = "F80",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/bmw/"
        "?search%5Bfilter_enum_model%5D%5B0%5D=m3"
        "&search%5Bfilter_float_year%3Afrom%5D=2014"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    pages = 5,
)

if __name__ == "__main__":
    print(">>> BMW M4 F82")
    run(CONFIG_M4)
    print("\n>>> BMW M3 F80")
    run(CONFIG_M3)
