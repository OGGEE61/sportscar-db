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

    # RULE 3b: a made-up serial number: the last 6 characters all the same (WBA85DP090N111111,
    # WDB4632741X000000) or ending in a run of 5 digits (JTDMF432101234567, ...PPP12345, 54321).
    # A real car with such a serial is about one in 100,000.
    serial = vin[-6:]
    if len(set(serial)) == 1 or vin[-5:] in "0123456789" or vin[-5:] in "9876543210":
        return False

    # RULE 4: the WMI (first 3 characters) must match a make in the DB (BMW, Audi, Merc, Porsche, Toyota, Alpina)
    valid_wmi = (
        r"^(WAU|WUA|TRU|WA1|"     # Audi
        r"WBA|WBS|WBY|WB[0-9A-Z]|5UX|5YM|3MW|3MF|" # BMW
        r"WAP|"                   # Alpina
        r"WDB|WDD|WDC|W1N|W1K|1MB|" # Mercedes
        r"VAG|VAD|"               # Mercedes G-Class built in Graz, Austria (Steyr-Daimler-Puch / Magna Steyr)
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


# Origin markets whose damaged cars are sold from auctions there (Copart, IAAI): such a car is
# offered in Poland before it is shipped, so it has no Polish plate and its price is not the
# Polish market's.
OVERSEAS_ORIGINS = ("USA", "USA/Kanada", "Kanada")


# Nearly new cars are dealer stock ("salonówki"), not the used-car market this project
# tracks. Applies to every model: scrapers skip them and the database hides their sightings.
DEALER_MAX_AGE_DAYS = 365
DEALER_MAX_KM = 20_000
# A car from this or last model year with delivery mileage is unsold stock, registered or not
DELIVERY_MAX_KM = 1_000


def is_dealer_new(year, mileage_km, first_registration_date=None, on=None) -> bool:
    """True for dealer stock: a car under a year old with under 20 000 km, or a car from
    this or last model year with under 1 000 km.

    Age comes from the first registration date when it is a valid date, else from the
    model year (same calendar year as `on` counts as under a year; older never does).
    Unknown mileage or age is never treated as dealer stock. `on` is the date the ad
    was seen (default today).
    """
    if mileage_km is None or mileage_km >= DEALER_MAX_KM:
        return False
    on = on or date.today()
    if mileage_km < DELIVERY_MAX_KM and year and year >= on.year - 1:
        return True
    if is_valid_first_registration_date(first_registration_date, today=on):
        return (on - date.fromisoformat(first_registration_date.strip())).days < DEALER_MAX_AGE_DAYS
    return bool(year) and year >= on.year


# VAG / VAD: G-Class built in Graz, Austria (Steyr-Daimler-Puch / Magna Steyr)
MERCEDES_WMI = ("WDB", "WDC", "WDD", "WDF", "W1K", "W1N", "W1V", "4JG", "55S", "VAG", "VAD")


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


# ── Damage stated in the ad's text ───────────────────────────────────────────
# Sellers often leave the portal's "damaged" box unticked and say it in the title or description.
# Only wording that offers the car in a damaged state counts; a repaired past damage ("miał
# uszkodzony przód, wymieniono…") is history, not the car's state, and is left alone.
_TAGS = re.compile(r"<[^>]+>")
_NOT_DAMAGED = r"(?:nie|bez|brak|żadn\w+|nigdy|nie\s*był\w*)\s+(?:\w+\s+){0,2}"
# Offers of cars standing at US insurance auctions (import brokers' templates)
_DAMAGE_AUCTION = re.compile(
    r"uszkodzenie auta\s*:|rodzaj szkody\s*:|dokument\s*:\s*salvage|salvage (?:title|certificate)|numer lota|"
    r"run\s*&\s*drive|primary damage|\bcopart\b|\biaai\b|(?:licytacji|aukcji)\s+firm\w*\s+ubezpieczeniow|"
    r"szacunkowy koszt zakupu wraz z transportem")
_DAMAGE_TITLE = re.compile(r"(?<!nie)uszkodz|(?<!nie)rozbit|po wypadku|po kolizji|do naprawy|do remontu|powypadk|\bdamaged\b|"
                           r"\b(?:mała|lekka|drobna)\s+szkoda")
_DAMAGE_OFFER = re.compile(
    r"(?:sprzedam|sprzedaż|oferuję|na sprzedaż)[^.!?]{0,60}uszkodzon|"
    r"(?:auto|samoch[oó]d|pojazd|egzemplarz)\s+(?:jest\s+)?(?:mocno\s+|lekko\s+)?uszkodzon|"
    r"(?:auto|samoch[oó]d|pojazd)\s+do\s+(?:naprawy|remontu|odbudowy)|"
    r"do naprawy (?:blacharskiej|lakierniczej|tył|tyln|przód|przedn|bok|zderzak|lamp)|"
    r"(?:lekko|mocno)\s+uszkodzon|uszkodzon[yae]\s+(?:lew[ya]|praw[ya]|przód|tył|bok|podwozie)|"
    r"uszkodzenia\s+(?:widoczne|jak)\s+na\s+zdj|w\s+stanie\s+uszkodzonym|"
    r"po\s+(?:kolizji|wypadku|stłuczce),?\s+do\s+naprawy|uwaga\s*:?\s*pojazd uszkodzon|"
    r"uszkodzon\w*\s+(?:jak\s+|widoczn\w*\s+)?na\s+zdj|"
    r"(?:auto|samoch[oó]d|pojazd)\s+(?:\w+\s+)?(?:ma|posiada)\s+(?:\w+\s+){0,4}uszkodzeni|"
    r"(?:auto|samoch[oó]d)\s+z\s+(?:lekk|mał|drobn|niewielk)\w*\s+szkod|"
    r"sprowadzon\w*,\s*uszkodzon|wizualnie\s+po\s+(?:obcier|stłucz|kolizj)|"
    r"uszkodzenia\s+to\s+(?:podwozie|przód|tył|bok)|"
    r"(?:przód|tył|bok|zderzak)\s+do\s+(?:\w+\s+)?(?:poprawki|naprawy)")
# The same sentence says the damage is in the past or was repaired
_DAMAGE_PAST = re.compile(
    r"napraw(?:i|ion|a\b|ie\b|ą\b)|wymieni|odbudow|usunięt|zrobion|miał\w*\s|był\w*\s|został\w*\s|"
    r"kupion\w*\s|sprowadzon\w*\s+(?:\w+\s+){0,6}jako|kilka lat temu|w przeszłości|histori")


def damage_in_text(title, description):
    """The wording that offers the car as damaged, or None.

    For ads whose seller did not tick the portal's "damaged" box. Returns a short quote (shown
    with the "Uszkodzony" marker), so a wrong match can be seen and dismissed on the car's page.
    """
    title = " ".join(_TAGS.sub(" ", title or "").lower().split())
    text = " ".join(_TAGS.sub(" ", description or "").lower().replace("&amp;", "&").split())
    if (m := _DAMAGE_TITLE.search(title)) and not re.search(_NOT_DAMAGED + r"(?:uszkodz|rozbit)", title):
        return title[max(0, m.start() - 30):m.end() + 30].strip()
    if m := _DAMAGE_AUCTION.search(text):
        return text[max(0, m.start() - 20):m.end() + 60].strip()
    for sentence in re.split(r"(?<=[.!?])\s+|\s[-–•*]\s", text):
        m = _DAMAGE_OFFER.search(sentence)
        if not m:
            continue
        # The past tense counts only near the match: a long sentence without stops ("…uszkodzony jak
        # na zdjęciach … w carfax wcześniej nic nie było") is not history because of a far-off "było"
        near = sentence[max(0, m.start() - 80):m.end() + 80]
        if re.search(_NOT_DAMAGED + r"uszkodz", sentence) or _DAMAGE_PAST.search(near.replace("do naprawy", "")):
            continue
        return sentence[max(0, m.start() - 40):m.end() + 60].strip()
    return None


# ── Import offers of brokers ──────────────────────────────────────────────────
# A broker lists a car still at an auction or a dealer abroad (USA, Canada, Japan, Korea): the price
# is an estimate of what the car would cost to buy and bring, not a price of a car in Poland. Its
# sightings are kept (the VIN stays known) and left out of the market data (excluded_reason
# 'import_offer'). A private seller's "zdjęcia z aukcji do wglądu" is a car already imported: not this.
_IMPORT_OFFER = re.compile(
    r"cena,? za którą zakupimy samoch[oó]d|propozycj\w+ do sprowadzenia|szac\w+ koszt\w* zakupu|"
    r"oferta dotyczy importu samochodu|dostępny do zakupu i (?:bezpośredniego )?importu|do wylicytowania|"
    r"importu z aukcji|inspekcji przed licytacją|(?:aukcj|licytacj)\w*\s+firm\w*\s+ubezpieczeniow|"
    r"koszt\w* zakupu (?:i importu |wraz z )|z licytacji w usa|do kupienia na aukcji|"
    r"ofert\w* licytacji|dostępny na aukcji w|będzie licytowany|szacowana cena (?:z transportem|zakupu|podana)|"
    r"sprzedawany przez firmę ubezpieczeniową|wylicytowanie pojazdu|przedmiotem aukcji jest")


def is_import_offer(title, description) -> bool:
    """True for a broker's offer of a car still abroad, priced at an estimated cost of buying it."""
    text = " ".join(_TAGS.sub(" ", f"{title or ''} {description or ''}").replace("\\", "")
                    .replace("&nbsp;", " ").lower().split())
    return bool(_IMPORT_OFFER.search(text))
