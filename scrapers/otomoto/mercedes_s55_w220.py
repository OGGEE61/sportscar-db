import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Mercedes S55 AMG W220 (1999-2005).
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
    model   = "Klasa S",
    variant = "S55 AMG W220",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/s-klasa"
        "?search%5Bfilter_float_year%3Ato%5D=2005"
        "&search%5Bfilter_float_engine_capacity%3Afrom%5D=5300"
        "&search%5Bfilter_float_engine_capacity%3Ato%5D=5600"
        "&page={page}"
    ),
    title_must_contain = ["s55", "s 55", "55 amg", "55amg"],
    title_must_not_contain = [
        "c55", "c 55", "e55", "e 55", "cls55", "cls 55", "sl55", "sl 55",
        "slk55", "slk 55", "clk55", "clk 55", "g55", "g 55", "ml55", "ml 55",
        "cl55", "cl 55", "s500", "s 500", "s600", "s 600", "s63", "s 63", "s65", "s 65"
    ],
    defaults = {
        "power_hp":     500,
        "engine_cc":    5439,
        "engine_cyl":   8,
        "fuel_type":    "petrol",
        "transmission": "automatic",
        "drivetrain":   "RWD",
        "body_type":    "Sedan",
    }
)

if __name__ == "__main__":
    run(CONFIG)
