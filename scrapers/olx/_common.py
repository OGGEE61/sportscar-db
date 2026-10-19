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
