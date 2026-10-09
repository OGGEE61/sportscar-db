"""BMW Alpina (OLX) — run directly to scrape.

Hits OLX's BMW Alpina query. Filters out massive luxury barges (B7, XB7, XD7)
and rigorously validates that each listing is a genuine Alpina with WAP manufacturer VIN.
"""
import sys, os
_scrapers_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scrapers_dir not in sys.path:
    sys.path.insert(0, _scrapers_dir)
from base_scraper import ScraperConfig, run


def validate_genuine_alpina(detail: dict) -> bool:
    """Strict validator for authentic Alpina vehicles.

    1. VIN is strictly required (reject listings without VIN).
    2. Post-1983 Alpinas are certified as an independent manufacturer by KBA 
       and have manufacturer WMI 'WAP' (Alpina Burkard Bovensiepen).
       A car with 'WBA' is a standard BMW (e.g. with Alpina wheels or body kit).
    3. Pre-1983 models had BMW chassis VINs with an authentic Alpina build plaque.
    """
    vin = (detail.get("vin") or "").strip().upper()
    if not vin or len(vin) < 11:
        print(f"  [reject-alpina] Brak poprawnego VIN (otrzymano: '{vin or 'BRAK'}') — odrzucono.")
        return False

    # Genuine Alpina WMI (post-1983 KBA manufacturer)
    if vin.startswith("WAP"):
        return True

    # Pre-1983 historical models had BMW chassis VINs with Alpina serial plates
    year = detail.get("year") or 0
    if year < 1983 and vin.startswith("WBA"):
        desc = (detail.get("raw_description") or "").lower()
        if "alpina" in desc and any(k in desc for k in ["tabliczk", "certyfikat", "numer alpina", "plaque"]):
            return True

    print(f"  [reject-alpina] VIN {vin} nie zaczyna się od WAP (Alpina) — odrzucono standardowe BMW / akcesoria.")
    return False


CONFIG = ScraperConfig(
    make    = "Alpina",
    model   = "BMW",
    variant = "Alpina",
    source  = "olx",
    list_url = (
        "https://www.olx.pl/motoryzacja/samochody/q-bmw-alpina/"
        "?search[filter_float_price:from]=25000"
        "&page={page}"
    ),
    title_must_contain = "alpina",
    title_must_not_contain = ["B7", "XB7", "XD7"],
    validator = validate_genuine_alpina,
    defaults = {
        "make": "Alpina",
    },
)

if __name__ == "__main__":
    run(CONFIG)
