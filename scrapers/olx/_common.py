"""Helpers shared by the OLX scrapers."""


def min_power_validator(min_hp: int, label: str):
    """Reject listings whose stated power is below min_hp.

    OLX has no engine-power filter (otomoto does), so weaker base models that
    share the model name are dropped here. Listings without a stated power pass.
    """
    def validate(detail: dict) -> bool:
        power = detail.get("power_hp") or 0
        if power and power < min_hp:
            print(f"  [reject-{label}] {power} KM < {min_hp} KM -- not a {label}.")
            return False
        return True
    return validate


def all_of(*validators):
    """Combine validators (None entries ignored): a listing must pass every one."""
    checks = [v for v in validators if v]
    return lambda detail: all(v(detail) for v in checks)



def engine_cc_validator(min_cc: int | None, max_cc: int | None, label: str):
    """Reject listings whose stated engine capacity is outside [min_cc, max_cc]."""
    def validate(detail: dict) -> bool:
        cc = detail.get("engine_cc") or 0
        if cc and ((min_cc and cc < min_cc) or (max_cc and cc > max_cc)):
            print(f"  [reject-{label}] {cc} cm3 outside {min_cc}-{max_cc} -- not a {label}.")
            return False
        return True
    return validate


def year_required(label: str):
    """Reject listings without a model year.

    OLX text searches also return toys, parts and tools that mention the model
    name; real car ads always carry a year in their parameters.
    """
    def validate(detail: dict) -> bool:
        if detail.get("year"):
            return True
        print(f"  [reject-{label}] no model year -- not a car ad.")
        return False
    return validate


def olx_url(make: str, models: list[str], *, year_from=None, year_to=None,
            power_from=None, power_to=None, size_from=None, size_to=None) -> str:
    """OLX list URL (with a {page} placeholder) using OLX's own filters.

    `models` are OLX model slugs (filter_enum_model, e.g. 'cayman', 'rs4-avant').
    Filtering by model, year, power (HP) and engine size (cm3) on OLX's side keeps
    toys, parts and look-alike cars out of the result pages, so far fewer pages and
    detail requests are needed. Results are newest first, which lets the scraper
    stop at the first page of already-known listings. Ads that leave a filtered
    field (e.g. power) blank are not returned, same as the otomoto URLs.
    """
    params = [f"search[filter_enum_model][{i}]={m}" for i, m in enumerate(models)]
    for name, lo, hi in (("year", year_from, year_to), ("enginepower", power_from, power_to),
                         ("enginesize", size_from, size_to)):
        if lo:
            params.append(f"search[filter_float_{name}:from]={lo}")
        if hi:
            params.append(f"search[filter_float_{name}:to]={hi}")
    params.append("search[order]=created_at:desc")
    return f"https://www.olx.pl/motoryzacja/samochody/{make}/?" + "&".join(params) + "&page={page}"
