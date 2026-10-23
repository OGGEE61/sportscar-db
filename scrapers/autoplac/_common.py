"""Helpers shared by the autoplac.pl scrapers."""
from urllib.parse import quote


def autoplac_url(make: str | None = None, model: str | None = None, *, query=None,
                 year_from=None, year_to=None, power_from=None, power_to=None,
                 cc_from=None, cc_to=None) -> str:
    """autoplac list URL (with a {page} placeholder) using autoplac's own filters.

    `make`/`model` are autoplac path slugs (e.g. 'bmw', 'm-3', 'seria-1'), `query`
    a full-text search. Power is in HP, engine size in cm3. Pages past the last one wrap to page 1;
    run() stops at the reported result count.
    """
    path = "/".join(p for p in ("samochody-osobowe", make, model) if p)
    params = [f"fullTextQuery={quote(query)}"] if query else []
    for name, lo, hi in (("year", year_from, year_to), ("enginePower", power_from, power_to),
                         ("engineCapacity", cc_from, cc_to)):
        if lo:
            params.append(f"{name}From={lo}")
        if hi:
            params.append(f"{name}To={hi}")
    params.append("p={page}")
    return f"https://autoplac.pl/oferty/{path}?" + "&".join(params)
