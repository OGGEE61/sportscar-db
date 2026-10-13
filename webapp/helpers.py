
"""Shared helpers: validation, parsing, paths and environment flags."""
import os
import re
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_PRODUCTION = bool(os.environ.get("VERCEL"))


def NOW():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def is_plausible_vin(vin: str) -> bool:
    """Basic sanity check — see base_scraper.py for rationale."""
    if not vin or len(vin) != 17:
        return False
    vin = vin.upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        return False
    if len(set(vin)) < 5:
        return False
    if max(vin.count(c) for c in set(vin)) >= 7:
        return False
        
    # ZASADA 1: Brak liter I, O, Q jest już zapewniony przez główny regex
    
    # ZASADA 2: Odrzucamy cenzurę (np. "XXXX") na końcu numeru
    if "X" in vin[-4:]:
        return False
        
    # ZASADA 3: Końcówka (VIS) musi kończyć się cyframi, ale ze względu na nowe normy 
    # BMW (braki numerów seryjnych) wymagamy minimum 2 cyfr zamiast 4
    if not re.search(r"[0-9]{2}$", vin):
        return False
        
    # ZASADA 4: WMI (pierwsze 3 znaki) musi pasować do marek z bazy (BMW, Audi, Merc, Porsche, Toyota, Alpina)
    valid_wmi = (
        r"^(WAU|WUA|TRU|WA1|"     # Audi
        r"WBA|WBS|WBY|WB[0-9A-Z]|5UX|5YM|3MW|3MF|" # BMW
        r"WAP|"                   # Alpina
        r"WDB|WDD|WDC|W1N|W1K|1MB|" # Mercedes
        r"WP0|WP1|"               # Porsche
        r"JT|"                    # Toyota
        r"1C6|3C6|"               # RAM
        r"JH[A-Z0-9]|SH[A-Z0-9]|1HG|2HG|" # Honda
        r"1F[A-Z0-9]|1Z[A-Z0-9]|3F[A-Z0-9]|WF[A-Z0-9])" # Ford
    )
    if not re.match(valid_wmi, vin):
        return False

    return True

def is_valid_registration_plate(plate: str) -> bool:
    """Validate a Polish / EU registration plate string.

    Rules:
      - 4 to 8 characters max after removing whitespace, hyphens, dots
      - Pure uppercase ASCII alphanumeric [A-Z0-9] (no special chars or Polish diacritics)
      - Must contain at least one letter and at least one digit
      - Reject dummy text, blacklisted placeholders, and all-identical characters
    """
    if not plate or not isinstance(plate, str):
        return False
    cleaned = re.sub(r"[\s\-\.]", "", plate).upper()
    if not (4 <= len(cleaned) <= 8):
        return False
    if not re.fullmatch(r"[A-Z0-9]+", cleaned):
        return False
    if not (re.search(r"[A-Z]", cleaned) and re.search(r"[0-9]", cleaned)):
        return False
    blacklist = ["SALONPL", "BRAK", "AUTO", "TEST", "NIE", "XXX", "ALEJA", "STAN", "NOWY", "DEALER", "BEZWYP"]
    if any(bad in cleaned for bad in blacklist):
        return False
    if len(set(cleaned)) <= 1:
        return False
    return True


def safe_int(val, default=None):
    try:
        if val is None or str(val).strip() == "": return default
        return int(float(str(val).replace(" ", "").replace(",", ".")))
    except (ValueError, TypeError):
        return default

def safe_float(val, default=None):
    try:
        if val is None or str(val).strip() == "": return default
        return float(str(val).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return default


PHOTOS_DIR = os.path.join(ROOT_DIR, "static", "photos")
try:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
except OSError:
    pass  # Serverless read-only filesystem (e.g. Vercel)
