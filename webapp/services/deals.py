"""The newest listings around Poznań, each priced against the market (the /deals page).

One query loads the latest sighting of every listing seen in the last COMPARE_DAYS days. Those
listings, sold ones included, are the market: a listing's price is compared with the median price
of the same make, model and variant from model years close to it (YEAR_WINDOWS), and only when
there are at least MIN_COMPARABLES other cars to compare with. A car
counts once (its newest listing), so a car relisted on another site does not vote twice, and the
listing never votes on itself. Damaged cars are neither compared nor part of the market.
"""
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from webapp.helpers import damaged_ad_sql
from webapp.regions import REGION_NAME_TO_CODE, WIELKOPOLSKA_PLACES, km_from_poznan, place_name, resolve_region

COMPARE_DAYS = 180
MIN_COMPARABLES = 5
# Model years compared, widened one step at a time until there are MIN_COMPARABLES cars. Never
# wider: one variant can span decades (a 1990 and a 2020 G-Class) and their prices say nothing
# about each other.
YEAR_WINDOWS = (1, 2, 3)
DEAL_BELOW = -0.10   # at least 10% under the median: a deal
PRICEY_ABOVE = 0.10  # over 10% above the median: expensive
MAX_RESULTS = 100

RANGES = {"25": 25, "50": 50, "100": 100, "woj": None}  # None: the whole Wielkopolskie voivodeship
PERIODS = {"7": 7, "30": 30, "90": 90}
SORTS = ("new", "deal")

LISTINGS_SQL = """
WITH listing AS (
  SELECT o.vin, o.source, o.source_listing_id, o.source_url, o.title, o.price_pln, o.mileage_km,
         o.location_city, o.location_region, o.observed_at, o.removed_at,
         MIN(o.observed_at) OVER (PARTITION BY o.source, o.source_listing_id) AS listed_at,
         ROW_NUMBER() OVER (PARTITION BY o.source, o.source_listing_id
                            ORDER BY o.observed_at DESC, o.id DESC) AS rn
  FROM listing_observations o
  WHERE o.excluded_reason IS NULL AND o.source_listing_id IS NOT NULL
)
SELECT l.*, v.make, v.model, v.variant, v.year, v.power_hp, v.photo, v.vin_status,
       """ + damaged_ad_sql("l") + """ AS damaged
FROM listing l JOIN vehicles v ON v.vin = l.vin
WHERE l.rn = 1 AND l.price_pln > 0 AND l.observed_at >= datetime('now', ?)
"""


def load_listings(conn) -> list:
    """The latest sighting of every listing seen in the last COMPARE_DAYS days (one query)."""
    return [dict(r) for r in conn.execute(LISTINGS_SQL, (f"-{COMPARE_DAYS} days",)).fetchall()]


def listing_region(region, city):
    """Voivodeship code of a listing: its region field, the region named after the comma in the
    city ('Wijewo, Wielkopolskie'), or the region of a known city."""
    code = resolve_region(region)
    if code:
        return code
    parts = (city or "").split(",")
    if len(parts) > 1:
        code = REGION_NAME_TO_CODE.get(parts[-1].strip().lower())
        if code:
            return code
    place = place_name(city)
    return resolve_region(None, place) or ("PL-WP" if place in WIELKOPOLSKA_PLACES else None)


def market(listings: list) -> dict:
    """(make, model, variant) -> [(year, price, vin)], one entry per car (its newest listing)."""
    newest = {}
    for item in listings:
        if item.get("damaged"):
            continue
        held = newest.get(item["vin"])
        if not held or (item["observed_at"] or "") > (held["observed_at"] or ""):
            newest[item["vin"]] = item
    groups = defaultdict(list)
    for item in newest.values():
        groups[(item["make"], item["model"], item["variant"])].append((item["year"], item["price_pln"], item["vin"]))
    return groups


def compare(item: dict, groups: dict):
    """{"median", "diff" (fraction, negative = cheaper), "count", "basis"} or None when there are
    too few comparable cars (or the car is damaged)."""
    if item.get("damaged"):
        return None
    others = [(y, p) for y, p, vin in groups.get((item["make"], item["model"], item["variant"]), [])
              if vin != item["vin"]]
    year = item.get("year")
    if not year:
        return None
    for window in YEAR_WINDOWS:
        prices = [p for y, p in others if y and abs(y - year) <= window]
        if len(prices) >= MIN_COMPARABLES:
            break
    else:
        return None
    basis = f"rocznik ±{window}"
    median = statistics.median(prices)
    return {"median": round(median), "diff": item["price_pln"] / median - 1, "count": len(prices), "basis": basis}


def verdict(diff):
    """'deal', 'fair', 'pricey' or None (no comparison)."""
    if diff is None:
        return None
    return "deal" if diff <= DEAL_BELOW else "pricey" if diff > PRICEY_ABOVE else "fair"


def _age_days(stamp, now):
    """Whole days since a 'YYYY-MM-DD HH:MM:SS' UTC stamp, or None."""
    try:
        return max(0, (now - datetime.strptime(stamp[:19], "%Y-%m-%d %H:%M:%S")).days)
    except (TypeError, ValueError):
        return None


def poznan_deals(listings: list, range_key="50", period_key="30", sort="new", now=None) -> dict:
    """Active listings around Poznań listed in the period, newest first (or best deal first).

    Returns {"items": [...], "total": n, "unknown_place": n}; unknown_place counts the active
    Wielkopolska listings in the period whose distance is unknown (shown only for "woj").
    """
    max_km = RANGES.get(range_key, RANGES["50"])
    days = PERIODS.get(period_key, PERIODS["30"])
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    groups = market(listings)

    picked, unknown_place = [], 0
    for item in listings:
        if item.get("removed_at") or (item.get("listed_at") or "") < since:
            continue
        km = km_from_poznan(item.get("location_city"))
        in_region = listing_region(item.get("location_region"), item.get("location_city")) == "PL-WP"
        if km is None and in_region:
            unknown_place += 1
        if max_km is None:
            if not in_region:
                continue
        elif km is None or km > max_km:
            continue
        cmp = compare(item, groups)
        picked.append(dict(item, km=km, place=place_name(item.get("location_city")) or None, cmp=cmp,
                           verdict=verdict(cmp["diff"] if cmp else None),
                           age_days=_age_days(item.get("listed_at"), now)))

    # A car listed on two sites shows once, by its newest listing
    picked.sort(key=lambda d: d.get("listed_at") or "", reverse=True)
    seen, items = set(), []
    for d in picked:
        if d["vin"] not in seen:
            seen.add(d["vin"])
            items.append(d)
    if sort == "deal":
        items.sort(key=lambda d: d["cmp"]["diff"] if d["cmp"] else float("inf"))
    return {"items": items[:MAX_RESULTS], "total": len(items), "unknown_place": unknown_place}
