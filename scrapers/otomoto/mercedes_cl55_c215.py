import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Mercedes CL55 AMG C215 (1999-2006).
5.4 V8 Kompressor (or NA early on), 360-500 HP, RWD.
"""
import sys, os
_dir = os.path.dirname(__file__)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, os.path.join(os.path.dirname(_dir), "scrapers"))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "CL",
    variant = "CL55 AMG C215",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/cl"
        "?search%5Bfilter_float_year%3Ato%5D=2006"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=5300"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=5600"
        "&page={page}"
    ),
    title_must_contain = ["cl55", "cl 55", "55 amg", "55amg"],
    title_must_not_contain = ["cl500", "cl 500", "cl600", "cl 600", "cl63", "cl 63", "cl65", "cl 65"],
    defaults = {
        "power_hp":     500,
        "engine_cc":    5439,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
