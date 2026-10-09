"""BMW M4 F82 / M3 F80 (2014–2020) — run directly to scrape.

F80 = M3 sedan, F82 = M4 coupe, F83 = M4 cabrio.
Both share the S55 3.0 biturbo engine (425/431 HP).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG_M4 = ScraperConfig(
    make    = "BMW",
    model   = "M4",
    variant = "F82",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m4"
        "?search%5Bfilter_float_year%3Afrom%5D=2014"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    min_year = 2014,
    max_year = 2020,
    defaults = {
        "power_hp":     431,
        "engine_cc":    2979,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    },
)

if __name__ == "__main__":
    run(CONFIG_M4)
