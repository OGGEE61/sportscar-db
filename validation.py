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
        
    # RULE 1: the main regex already excludes the letters I, O, Q
    
    # RULE 2: reject a masked ending (e.g. "XXXX")
    if "X" in vin[-4:]:
        return False
        
    # RULE 3: the VIS must end in digits; because of newer BMW serial numbers
    # (which contain letters) require at least 2 trailing digits instead of 4
    if not re.search(r"[0-9]{2}$", vin):
        return False
        
    # RULE 4: the WMI (first 3 characters) must match a make in the DB (BMW, Audi, Merc, Porsche, Toyota, Alpina)
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


# Listings that are nearly new with a delivery mileage are dealer stock, not the
# used-car market this project tracks
DEALER_M2_MAX_AGE_DAYS = 365
DEALER_M2_MAX_KM = 20_000


def is_dealer_new_m2(model, year, mileage_km, first_registration_date=None, on=None) -> bool:
    """is_dealer_new for an M2; any other model is never dealer stock here."""
    if (model or "").strip().upper() != "M2":
        return False
    return is_dealer_new(year, mileage_km, first_registration_date, on)


def is_dealer_new(year, mileage_km, first_registration_date=None, on=None) -> bool:
    """True for a car less than a year old with under 20 000 km (dealer stock).

    Age comes from the first registration date when it is a valid date, else from the
    model year (same calendar year as `on` counts as under a year; older never does).
    Unknown mileage or age is never treated as dealer stock. `on` is the date the ad
    was seen (default today).
    """
    if mileage_km is None or mileage_km >= DEALER_M2_MAX_KM:
        return False
    on = on or date.today()
    if is_valid_first_registration_date(first_registration_date, today=on):
        return (on - date.fromisoformat(first_registration_date.strip())).days < DEALER_M2_MAX_AGE_DAYS
    return bool(year) and year >= on.year


# VAG: G-Class built by Steyr-Daimler-Puch
MERCEDES_WMI = ("WDB", "WDC", "WDD", "WDF", "W1K", "W1N", "W1V", "4JG", "55S", "VAG")


def is_other_mercedes_chassis(vin, chassis) -> bool:
    """True when a European Mercedes VIN (WDB2110771...) names a chassis other than `chassis`.

    A VIN of another make (a typo or a wrong number in the ad) is also ruled out. Otherwise only
    positions 4-6 in digits count: US-spec VINs (WDDHF...) code the model in letters, so they
    and a missing VIN are never ruled out.
    """
    vin = (vin or "").strip().upper()
    if len(vin) == 17 and not vin.startswith(MERCEDES_WMI):
        return True
    code = vin[3:6]
    return len(code) == 3 and code.isdigit() and code != chassis
