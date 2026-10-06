"""Mercedes-Benz CLK 63 AMG W209 (2006–2009) — run directly to scrape.

W209 CLK 63 AMG: 6.2 V8 M156, 481 HP (standard) / 507 HP (Black Series).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run

CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa CLK",
    variant = "W209 CLK 63 AMG",
    source  = "otomoto",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/clk-klasa"
        "?search%5Bfilter_float_year%3Afrom%5D=2006"
        "&search%5Bfilter_float_year%3Ato%5D=2009"
        "&search%5Bfilter_float_engine_power%3Afrom%5D=470"
        "&page={page}"
    ),
    title_must_contain = ["CLK 63", "CLK63", "63 AMG"],
    defaults = {
        "power_hp":     481,
        "engine_cc":    6208,
        "fuel_type":    "Petrol",
        "drivetrain":   "RWD",
        "transmission": "Automatic",
        "body_type":    "Coupe",
    }
)

if __name__ == "__main__":
    run(CONFIG)
