"""SportsCar DB web app: Flask app factory and blueprint registration."""
import hashlib
import json
import os
import time

from flask import Flask

from db import get_db
from webapp.services import r2
from webapp.regions import location
from webapp.helpers import IS_PRODUCTION, ROOT_DIR, is_plausible_vin, is_valid_registration_plate, plain_text


_NOTIF_CACHE = {"at": 0.0, "data": None}
_NOTIF_TTL = 60  # seconds


def _static_version(filename):
    """Short content hash of a static file, used to bust browser/CDN caches when it changes."""
    try:
        with open(os.path.join(ROOT_DIR, "static", filename), "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except OSError:
        return "0"


def invalidate_notifications():
    """Drop the cached badge counts (call after marking logs read / reviewing plates)."""
    _NOTIF_CACHE["data"] = None


def _inject_notifications():
    now = time.time()
    if _NOTIF_CACHE["data"] is not None and now - _NOTIF_CACHE["at"] < _NOTIF_TTL:
        return _NOTIF_CACHE["data"]
    unread_count = 0
    plates_count = 0
    try:
        conn = get_db()
        row = conn.execute("""
            SELECT (SELECT COUNT(*) FROM scraper_logs WHERE is_read = 0) AS unread,
                   (SELECT COUNT(*) FROM plate_review_queue WHERE status = 'pending') AS plates
        """).fetchone()
        conn.close()
        if row:
            unread_count, plates_count = row["unread"] or 0, row["plates"] or 0
    except Exception:
        pass
    data = dict(unread_notifications_count=unread_count, pending_plates_count=plates_count)
    _NOTIF_CACHE.update(at=now, data=data)
    return data


def media_url(path):
    """URL for a stored photo, loaded by the browser straight from R2: the public bucket URL
    with R2_PUBLIC_URL, else a presigned link made here (webapp.services.r2, no network).
    Only without R2 (local development) does it go through the /media route."""
    if not path:
        return ""
    public = os.environ.get("R2_PUBLIC_URL")
    if public:
        return f"{public.rstrip('/')}/{path}"
    return r2.presigned_url(path) or f"/media/{path}"


HEAVY_REQUEST_ROWS = 20000  # rows read by one request worth a line in the log


def _count_rows_read(app):
    """Every response says how many rows D1 read for it (X-D1-Rows-Read), and heavy requests are
    logged with their path, so whatever eats the daily read limit (5M rows on the free plan)
    can be found in the Vercel logs."""
    from flask import request
    from db import ROWS_READ

    @app.before_request
    def _reset_rows_read():
        ROWS_READ.reset()

    @app.after_request
    def _report_rows_read(response):
        n = ROWS_READ.count
        response.headers["X-D1-Rows-Read"] = str(n)
        if n >= HEAVY_REQUEST_ROWS:
            print(f"[d1] {n} rows read: {request.method} {request.path}", flush=True)
        return response


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(ROOT_DIR, "templates"),
        static_folder=os.path.join(ROOT_DIR, "static"),
    )

    app.secret_key = os.environ.get("SECRET_KEY")
    if not app.secret_key:
        if IS_PRODUCTION and os.environ.get("ADMIN_PASSWORD"):
            # A known fallback key would let anyone forge a logged-in session
            raise RuntimeError("SECRET_KEY must be set in production")
        app.secret_key = "fallback-dev-secret-key"
    # Lax blocks cross-site POSTs from carrying the session cookie (CSRF mitigation)
    app.config.update(
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=IS_PRODUCTION,
    )

    app.jinja_env.filters["fromjson"] = json.loads
    app.jinja_env.filters["plain_text"] = plain_text
    app.jinja_env.tests["plausible_vin"] = is_plausible_vin
    app.jinja_env.tests["valid_plate"] = is_valid_registration_plate
    app.jinja_env.globals["media_url"] = media_url
    app.jinja_env.globals["location"] = location
    app.jinja_env.globals["css_version"] = _static_version("style.css")

    from webapp.blueprints import api, auth, cepik, dashboard, deals, plates, review, vehicles
    for module in (auth, dashboard, deals, vehicles, review, plates, cepik, api):
        app.register_blueprint(module.bp)

    _count_rows_read(app)

    return app
