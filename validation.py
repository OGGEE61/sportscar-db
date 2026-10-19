"""VIN and registration-plate validation, shared by the scrapers and the web app.

This is the core of SportsCar DB: a VIN that passes `is_plausible_vin` becomes the
database key that links a scraped listing to a known car. Both sides must use this
one implementation so a VIN accepted by a scraper is never rejected by the app.
Change it only together with tests in tests/test_validation.py.
"""
import re
from datetime import date

# Used both to validate a whole string and to find VIN candidates inside free text
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")


def is_plausible_vin(vin: str) -> bool:
    """Return True if vin looks like a real VIN.

    We can't use the ISO check digit for European cars (only NA-market VINs
    have a mandated check digit at position 9), so we use softer heuristics:
      - 17 chars, valid charset
      - at least 5 distinct characters  (rejects all-same-digit fakes)
      - no single character appears 7+ times (rejects heavily-repeated fakes)
    """
    if not vin or len(vin) != 17:
        return False
    vin = vin.upper()
    if not VIN_RE.fullmatch(vin):
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
    blacklist = ["SALONPL", "BRAK", "AUTO", "TEST", "NIE", "XXX", "ALEJA", "STAN", "NOWY", "DEALER", "BEZWYP",
                 "BMW", "M40I", "XDRIVE"]  # model names mistaken for plates
    if any(bad in cleaned for bad in blacklist):
        return False
    if len(set(cleaned)) <= 1:
        return False
    return True


MIN_FIRST_REGISTRATION_YEAR = 1980


def is_valid_first_registration_date(value, today=None) -> bool:
    """True for an ISO date (YYYY-MM-DD) that is not in the future and not before 1980."""
    if not value or not isinstance(value, str):
        return False
    try:
        d = date.fromisoformat(value.strip())
    except ValueError:
        return False
    return d.year >= MIN_FIRST_REGISTRATION_YEAR and d <= (today or date.today())
