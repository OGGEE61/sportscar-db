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
    """Strict validator for authentic sports Alpina vehicles.

    1. VIN is strictly required (reject listings without VIN).
    2. Post-1983 Alpinas are certified as an independent manufacturer by KBA 
       and have manufacturer WMI 'WAP' (Alpina Burkard Bovensiepen).
       A car with 'WBA' is a standard BMW (e.g. with Alpina wheels or body kit).
    3. Pre-1983 models had BMW chassis VINs with an authentic Alpina build plaque.
    4. Exclude 2.0 diesel models (early 4-cyl D3 2.0d / 200-214 HP).
    5. Exclude luxury barges: Series 7, X7 (B7, XB7, XD7).
    """
    vin = (detail.get("vin") or "").strip().upper()
    if not vin or len(vin) < 11:
        print(f"  [reject-alpina] Brak poprawnego VIN (otrzymano: '{vin or 'BRAK'}') — odrzucono.")
        return False

    # Check 7 / X7 in title
    title = (detail.get("title") or "").lower()
    for barge in ["b7", "xb7", "xd7", "alpina 7", "seria 7", "serii 7", "740", "750", "760"]:
        if barge in title:
            print(f"  [reject-alpina] Wykluczony model luksusowy ('{barge}') — odrzucono.")
            return False

    # Exclude 2.0 diesel (e.g. early D3 2.0d / Bi-Turbo 4-cyl, 200-214 HP)
    fuel = (detail.get("fuel_type") or "").lower()
    engine_cc = detail.get("engine_cc") or 0
    power_hp = detail.get("power_hp") or 0
    desc = (detail.get("raw_description") or "").lower()

    is_diesel = "diesel" in fuel or "diesel" in desc or "2.0d" in title or "2.0 d" in title or "2.0d" in desc
    if is_diesel and ((0 < engine_cc <= 2200) or (0 < power_hp <= 230) or "2.0d" in title or "2.0d" in desc):
        print(f"  [reject-alpina] 2.0 Diesel wykluczony ({power_hp} KM, {engine_cc} cc) — odrzucono.")
        return False

    # Genuine Alpina WMI (post-1983 KBA manufacturer)
    if vin.startswith("WAP"):
        return True

    # Pre-1983 historical models had BMW chassis VINs with Alpina serial plates
    year = detail.get("year") or 0
    if year < 1983 and vin.startswith("WBA"):
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
