
"""Shared helpers: parsing, paths and environment flags (validation lives in /validation.py)."""
import os
from datetime import datetime

from validation import is_plausible_vin, is_valid_registration_plate  # noqa: F401  (re-exported)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_PRODUCTION = bool(os.environ.get("VERCEL"))


def NOW():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


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
