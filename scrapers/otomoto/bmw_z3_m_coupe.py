import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""BMW Z3 M (1997-2002) - Coupe & Roadster
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "BMW",
    model   = "Z3",
    variant = "Z3 M",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/bmw/z3"
        "?search%5Bfilter_float_engine_power%3Afrom%5D=300"
        "&page={page}"
    ),
    defaults = {
        "power_hp":     321,
        "engine_cc":    3201,
        "engine_cyl":   6,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "RWD",
    },
)

if __name__ == "__main__":
    run(CONFIG)
