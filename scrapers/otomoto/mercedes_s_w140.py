"""Mercedes-Benz S-Class W140 (1991–1998), all engines — run directly to scrape."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(__file__))
from base_scraper import ScraperConfig, run
from validation import is_other_mercedes_chassis


def is_w140(detail: dict) -> bool:
    return not is_other_mercedes_chassis(detail.get("vin"), "140")


CONFIG = ScraperConfig(
    make    = "Mercedes-Benz",
    model   = "Klasa S",
    variant = "W140",
    source  = "otomoto",
    model_id = "s_w140",
    list_url = (
        "https://www.otomoto.pl/osobowe/mercedes-benz/s-klasa"
        "?search%5Bfilter_enum_generation%5D=gen-w140-1992-1998"
        "&page={page}"
    ),
    min_year = 1991,
    max_year = 1999,
    validator = is_w140,
    defaults = {
        "drivetrain":   "RWD",
        "transmission": "automatic",
    },
)

if __name__ == "__main__":
    run(CONFIG)
