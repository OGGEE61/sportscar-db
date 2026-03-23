"""BMW M4 F82 / M3 F80 (2014–2020) — run directly to scrape.

F80 = M3 sedan, F82 = M4 coupe, F83 = M4 cabrio.
Both share the S55 3.0 biturbo engine (425/431 HP).
"""
import sys, os
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
    pages = 5,
    defaults = {
        "power_hp":     431,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
    },
)

CONFIG_M3 = ScraperConfig(
    make    = "BMW",
    model   = "M3",
    variant = "F80",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/m3"
        "?search%5Bfilter_float_year%3Afrom%5D=2014"
        "&search%5Bfilter_float_year%3Ato%5D=2020"
        "&page={page}"
    ),
    pages = 5,
    defaults = {
        "power_hp":     431,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
    },
)

if __name__ == "__main__":
    print(">>> BMW M4 F82")
    run(CONFIG_M4)
    print("\n>>> BMW M3 F80")
    run(CONFIG_M3)
