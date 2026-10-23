"""X3 G01 family on every market: X3 M (F97) and X3 M40i, told apart by VIN.

Sellers mix the two up (an M40i filed as X3 M, an X3 M titled "M40i", stated power
off by a model). The VIN maker code settles it: BMW M GmbH builds the X3 M (WBS EU,
5YM US), regular BMW the M40i (WBA EU, 5UX US). The two scrapers of a market search
the same URLs, so a car filed under the wrong one is still seen by the scraper it
belongs to and neither marks the other's ads sold.
"""
import importlib

M_WMI = ("WBS", "5YM")
REGULAR_WMI = ("WBA", "5UX")

# The module names of the two siblings in a market's package (olx/, otomoto/, autoplac/)
_SIBLINGS = {"X3 M": "bmw_x3_m_f97", "M40i": "bmw_x3_m40i_g01"}


def classify_x3_g01(detail: dict) -> str | None:
    """'X3 M', 'M40i' or None when the VIN does not settle it (no VIN, diesel, other car)."""
    vin = (detail.get("vin") or "").strip().upper()
    if len(vin) != 17 or "diesel" in (detail.get("fuel_type") or "").lower():
        return None
    if vin.startswith(M_WMI):
        return "X3 M"
    if vin.startswith(REGULAR_WMI):
        # A regular X3 G01 with a 3.0 petrol is an M40i; 20i/30i are 2.0 with 184-252 HP.
        # Power above 430 is a seller typing X3 M figures, so it does not count against it.
        cc = detail.get("engine_cc") or 0
        power = detail.get("power_hp") or 0
        if cc and not 2900 <= cc <= 3100:
            return None
        if power and power < 320:
            return None
        return "M40i"
    return None


def reassign_x3_g01(market: str):
    """ScraperConfig.reassign for both X3 configs of `market`: the config the VIN says the car is."""
    def reassign(detail: dict):
        kind = classify_x3_g01(detail)
        if not kind:
            return None
        # Imported on use: the config modules import this one
        return importlib.import_module(f"{market}.{_SIBLINGS[kind]}").CONFIG
    return reassign


def x3_g01_power_validator(kind: str):
    """Fallback for ads the VIN does not settle (no VIN): keep the stated power in range.

    For markets whose searches are no longer split by power (the VIN does that now).
    Ads without a stated power pass.
    """
    def validate(detail: dict) -> bool:
        power = detail.get("power_hp") or 0
        if kind == "M40i" and power > 430:
            print(f"  [reject-m40i] {power} KM > 430 KM and no VIN to prove it is an M40i -- not an M40i.")
            return False
        if kind == "X3 M" and power and power < 440:
            print(f"  [reject-x3m] {power} KM < 440 KM and no VIN to prove it is an X3 M -- not an X3 M.")
            return False
        return True
    return validate
