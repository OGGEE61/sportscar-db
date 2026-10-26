
"""Shared helpers: parsing, paths and environment flags (validation lives in /validation.py)."""
import html
import os
from datetime import datetime, timezone

from jinja2.utils import htmlsafe_json_dumps

from validation import is_plausible_vin, is_valid_first_registration_date, is_valid_registration_plate  # noqa: F401  (re-exported)


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


def car_visible_sql(alias="v"):
    """SQL condition: the car has a sighting that is not excluded, or has no sightings at all.

    Dealer-stock M2 sightings (listing_observations.excluded_reason) stay in the database so
    their VINs remain known, but the dashboard, model analytics and /vehicles skip them. A car
    whose every sighting is excluded is hidden too.
    """
    return (f"NOT (EXISTS (SELECT 1 FROM listing_observations x WHERE x.vin = {alias}.vin AND x.excluded_reason IS NOT NULL) "
            f"AND NOT EXISTS (SELECT 1 FROM listing_observations x WHERE x.vin = {alias}.vin AND x.excluded_reason IS NULL))")
