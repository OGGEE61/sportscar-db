
"""Shared helpers: parsing, paths and environment flags (validation lives in /validation.py)."""
import html
import os
from datetime import datetime, timezone

from jinja2.utils import htmlsafe_json_dumps

from validation import OVERSEAS_ORIGINS, is_plausible_vin, is_valid_first_registration_date, is_valid_registration_plate  # noqa: F401  (re-exported)


def script_json(obj):
    """JSON safe to drop into a <script> block (escapes <, >, & and ').

    Scraped titles/cities end up in chart data; plain json.dumps would let a
    title containing '</script>' break out of the script tag.
    """
    return htmlsafe_json_dumps(obj)


def plain_text(value):
    """Scraped description as plain text: decode HTML entities left over from
    tag stripping (&nbsp;, &amp;); the template's autoescape does the rest."""
    return html.unescape(value) if value else value

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_PRODUCTION = bool(os.environ.get("VERCEL"))


def NOW():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def safe_int(val, default=None):
    try:
        if val is None or str(val).strip() == "": return default
        return int(float(str(val).replace(" ", "").replace(",", ".")))
    except (ValueError, TypeError):
        return default

def safe_float(val, default=None):
    try:
        if val is None or str(val).strip() == "": return default
        return float(str(val).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return default


PHOTOS_DIR = os.path.join(ROOT_DIR, "static", "photos")
try:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
except OSError:
    pass  # Serverless read-only filesystem (e.g. Vercel)


def damaged_ad_sql(alias):
    """SQL condition: this observation's ad is marked as damaged on its site."""
    return (f"EXISTS (SELECT 1 FROM damaged_listings d WHERE d.source = {alias}.source "
            f"AND d.source_listing_id = {alias}.source_listing_id)")


def damage_history_sql(alias="v"):
    """SQL condition: a condition report says the car is not accident free (e.g. a VIN check
    found it damaged abroad), whatever its current ads say."""
    return (f"EXISTS (SELECT 1 FROM condition_reports cr WHERE cr.vin = {alias}.vin "
            f"AND cr.accident_free = 0)")


def overseas_damaged_listing_sql(alias):
    """SQL condition on a pending_listings row: a damaged ad of a car from the USA or Canada,
    i.e. a car not yet brought to Poland. No plate to look for."""
    origins = ", ".join(f"'{o}'" for o in OVERSEAS_ORIGINS)
    return (f"(COALESCE({alias}.origin_market, '') IN ({origins}) AND EXISTS (SELECT 1 FROM damaged_listings d "
            f"WHERE d.source = {alias}.source AND d.source_listing_id = {alias}.source_listing_id))")


def abroad_sql(alias="v"):
    """SQL condition: the car is almost surely still abroad. It comes from the USA or Canada, an
    ad of it is marked damaged and it has no Polish plate (a plate means it was imported)."""
    origins = ", ".join(f"'{o}'" for o in OVERSEAS_ORIGINS)
    return (f"(COALESCE({alias}.origin_market, '') IN ({origins}) AND COALESCE({alias}.registration_plate, '') = '' "
            f"AND EXISTS (SELECT 1 FROM listing_observations fd WHERE fd.vin = {alias}.vin "
            f"AND {damaged_ad_sql('fd')}))")


PHOTO_PLATE_TAGS = ("photo extracted", "AI extracted plate")


def car_flags_sql(alias="v"):
    """SELECT columns of the markers every list shows next to a car (templates/_car_flags.html):
    flag_vin_status, flag_plate, flag_origin, flag_abroad (abroad_sql), flag_plate_from_photo,
    flag_sold_damaged, flag_damage_history,
    flag_damage_country,
    flag_cepik ('ok' | 'rollback' | 'stolen' | NULL without a report), flag_rollback_km,
    flag_ad ('active' while an ad is up, else when the last one disappeared; NULL without ads) and
    flag_tags (the car's other tags, '|'-separated; plate-from-photo, 'missing plates' and CEPiK tags are
    markers already).
    Every page that lists cars selects these, so a car is marked the same way everywhere."""
    a = alias
    tags = ", ".join(f"'{t}'" for t in PHOTO_PLATE_TAGS)
    return f"""{a}.vin_status AS flag_vin_status,
        {a}.registration_plate AS flag_plate,
        {a}.origin_market AS flag_origin,
        {abroad_sql(a)} AS flag_abroad,
        EXISTS (SELECT 1 FROM tags ft WHERE ft.vin = {a}.vin AND ft.tag IN ({tags})) AS flag_plate_from_photo,
        EXISTS (SELECT 1 FROM listing_observations fx WHERE fx.vin = {a}.vin AND {damaged_ad_sql("fx")}) AS flag_sold_damaged,
        {damage_history_sql(a)} AS flag_damage_history,
        (SELECT cr.country FROM condition_reports cr WHERE cr.vin = {a}.vin AND cr.accident_free = 0
           AND COALESCE(cr.country, '') <> '' ORDER BY cr.report_date DESC LIMIT 1) AS flag_damage_country,
        (SELECT CASE WHEN fc.is_stolen = 1 THEN 'stolen' WHEN fc.odometer_rollback = 1 THEN 'rollback' ELSE 'ok' END
           FROM cepik_reports fc WHERE fc.vin = {a}.vin) AS flag_cepik,
        (SELECT fc.rollback_diff_km FROM cepik_reports fc WHERE fc.vin = {a}.vin) AS flag_rollback_km,
        CASE WHEN EXISTS (SELECT 1 FROM listing_observations fa WHERE fa.vin = {a}.vin
                            AND fa.excluded_reason IS NULL AND fa.removed_at IS NULL) THEN 'active'
             ELSE (SELECT MAX(fa.removed_at) FROM listing_observations fa
                   WHERE fa.vin = {a}.vin AND fa.excluded_reason IS NULL) END AS flag_ad,
        (SELECT GROUP_CONCAT(fg.tag, '|') FROM tags fg WHERE fg.vin = {a}.vin AND fg.tag NOT IN ({tags}, 'missing plates')
           AND LOWER(fg.tag) NOT LIKE 'cepik%') AS flag_tags"""


def car_visible_sql(alias="v"):
    """SQL condition: the car has a sighting that is not excluded, or has no sightings at all.

    Dealer-stock M2 sightings (listing_observations.excluded_reason) stay in the database so
    their VINs remain known, but the dashboard, model analytics and /vehicles skip them. A car
    whose every sighting is excluded is hidden too.

    Written so that it stops at the car's first usable sighting (one or two index rows) instead
    of reading all its sightings: equivalent to "not (some excluded and none usable)".
    """
    return (f"(EXISTS (SELECT 1 FROM listing_observations x WHERE x.vin = {alias}.vin AND x.excluded_reason IS NULL) "
            f"OR NOT EXISTS (SELECT 1 FROM listing_observations x WHERE x.vin = {alias}.vin))")


def trend_line(points):
    """Least-squares line through (x, y) points, as its two end points, for a chart.

    Empty when under 3 points or all at one x: no meaningful line. y never goes below 0.
    """
    if len(points) < 3:
        return []
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    if not spread:
        return []
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / spread
    at = lambda x: max(0, round(mean_y + slope * (x - mean_x)))
    lo, hi = min(x for x, _ in points), max(x for x, _ in points)
    return [{"x": lo, "y": at(lo)}, {"x": hi, "y": at(hi)}]
