"""SportsCar DB web app: Flask app factory and blueprint registration."""
import json
import os
import time

from flask import Flask

from db import get_db
from webapp.helpers import IS_PRODUCTION, ROOT_DIR, is_plausible_vin, is_valid_registration_plate, plain_text


_NOTIF_CACHE = {"at": 0.0, "data": None}
_NOTIF_TTL = 60  # seconds


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
    """URL for a stored photo. With R2_PUBLIC_URL set the browser loads it
    straight from R2; otherwise it goes through the /media redirect route."""
    if not path:
        return ""
    public = os.environ.get("R2_PUBLIC_URL")
    if public:
        return f"{public.rstrip('/')}/{path}"
    return f"/media/{path}"


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
    app.context_processor(_inject_notifications)

    from webapp.blueprints import api, auth, cepik, dashboard, plates, review, vehicles
    for module in (auth, dashboard, vehicles, review, plates, cepik, api):
        app.register_blueprint(module.bp)

    return app
