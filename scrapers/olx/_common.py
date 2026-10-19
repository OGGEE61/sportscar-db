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
