"""Deals around Poznań: the newest active listings near the city, priced against the market."""
import time

from flask import Blueprint, current_app, make_response, render_template, request

from db import get_db
from webapp.services import deals

bp = Blueprint("deals", __name__)

_CACHE = {"at": 0.0, "rows": None}
_CACHE_TTL = 300  # seconds; the scrapers add listings a few times a day


def _listings():
    """All recent listings, memoised per instance (one D1 query of ~0.5 s)."""
    if current_app.testing:
        conn = get_db()
        try:
            return deals.load_listings(conn)
        finally:
            conn.close()
    now = time.time()
    if _CACHE["rows"] is None or now - _CACHE["at"] > _CACHE_TTL:
        conn = get_db()
        try:
            _CACHE.update(rows=deals.load_listings(conn), at=now)
        finally:
            conn.close()
    return _CACHE["rows"]


def _choices(args):
    range_key = args.get("km") if args.get("km") in deals.RANGES else "50"
    period_key = args.get("days") if args.get("days") in deals.PERIODS else "30"
    sort = args.get("sort") if args.get("sort") in deals.SORTS else "new"
    return range_key, period_key, sort


@bp.route("/deals")
def deals_page():
    """Page shell only: the list loads from /api/deals."""
    range_key, period_key, sort = _choices(request.args)
    return render_template("deals.html", range_key=range_key, period_key=period_key, sort=sort,
                           ranges=deals.RANGES, periods=deals.PERIODS)


@bp.route("/api/deals")
def deals_list():
    range_key, period_key, sort = _choices(request.args)
    result = deals.poznan_deals(_listings(), range_key, period_key, sort)
    conn = get_db()
    try:
        result["items"] = deals.add_flags(conn, result["items"])
    finally:
        conn.close()
    resp = make_response(render_template("_deals_list.html", **result, range_key=range_key,
                                         period_key=period_key, sort=sort,
                                         deal_below=round(-deals.DEAL_BELOW * 100),
                                         compare_days=deals.COMPARE_DAYS))
    resp.headers["Cache-Control"] = "private, max-age=60"
    return resp
