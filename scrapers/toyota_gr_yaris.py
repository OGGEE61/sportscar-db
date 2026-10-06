"""Toyota GR Yaris (2020–) — run directly to scrape.

GR Yaris: 1.6L turbocharged 3-cylinder (G16E-GTS), 261 HP, AWD (GR-FOUR),
6-speed manual. Homologation special, produced in limited numbers.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Toyota",
    model   = "GR Yaris",
    variant = "GR Yaris",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/toyota/gr-yaris"
        "?search%5Bfilter_float_year%3Afrom%5D=2020"
        "&page={page}"
    ),
    title_must_contain = "GR Yaris",
    defaults = {
        "power_hp":     261,
        "engine_cc":    1618,
        "engine_cyl":   3,
        "fuel_type":    "petrol",
        "transmission": "manual",
        "drivetrain":   "AWD",
        "body_type":    "Hatchback",
    },
)

if __name__ == "__main__":
    run(CONFIG)
