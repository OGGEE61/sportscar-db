"""Mercedes-Benz G-Class W460 / W461 / W463, all engines, without the W464 (2018–) and the 2024
model — run directly to scrape.

Otomoto splits them by generation. The G55 AMG has its own scraper, so it is skipped here
(titled ads only: a G55 titled just "Klasa G" is not found by that scraper and stays here).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_other_mercedes_chassis


def old_g_chassis(detail: dict) -> bool:
    # W464 keeps 463 in its VIN, so the VIN can only rule out other models
    vin = detail.get("vin")
    return not all(is_other_mercedes_chassis(vin, chassis) for chassis in ("460", "461", "463"))


CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa G",
    variant = "W460 / W461 / W463",
    source  = "otomoto",
    model_id = "g_w463",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/g-klasa"
        "?search%5Bfilter_enum_generation%5D%5B0%5D=gen-w460-1979-1992"
        "&search%5Bfilter_enum_generation%5D%5B1%5D=gen-w461-1992-2022"
        "&search%5Bfilter_enum_generation%5D%5B2%5D=gen-w463-1992"
        "&page={page}"
    ),
    max_year = 2018,
    # "g 55 " keeps its space: without it the G 550 would match too
    title_must_not_contain = ["w464", "w 464", "w465", "w 465", "g55", "g 55 ", "55amg", "55 amg", "amg 55"],
    validator = old_g_chassis,
    defaults = {
        "drivetrain":   "AWD",
        "body_type":    "SUV",
    },
)

if __name__ == "__main__":
    run(CONFIG)
