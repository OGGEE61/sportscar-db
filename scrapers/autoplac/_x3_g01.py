"""X3 G01 family on autoplac: X3 M (F97) and X3 M40i, told apart by VIN.

Sellers mix the two up (an M40i filed as X3 M, an X3 M titled "M40i", stated power
off by a model). The VIN maker code settles it: BMW M GmbH builds the X3 M (WBS EU,
5YM US), regular BMW the M40i (WBA EU, 5UX US). Both configs search the same URLs
so a car filed under the wrong one is still seen by the scraper it belongs to.
"""
from autoplac._common import autoplac_url

X3_G01_URLS = [
    autoplac_url(query="bmw x3 m40"),
    autoplac_url("bmw", "x3", year_from=2017, year_to=2024, power_from=340),
]

M_WMI = ("WBS", "5YM")
REGULAR_WMI = ("WBA", "5UX")


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


def reassign_x3_g01(detail: dict):
    """ScraperConfig.reassign for both X3 configs: the config the VIN says the car is."""
    # Imported here: each config module imports this one
    from autoplac.bmw_x3_m40i_g01 import CONFIG as M40I
    from autoplac.bmw_x3_m_f97 import CONFIG as X3_M
    return {"X3 M": X3_M, "M40i": M40I}.get(classify_x3_g01(detail))
