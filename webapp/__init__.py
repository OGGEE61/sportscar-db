"""SportsCar DB web app: Flask app factory and blueprint registration."""
import json
import os

from flask import Flask

from db import get_db
from webapp.helpers import IS_PRODUCTION, ROOT_DIR, is_plausible_vin, is_valid_registration_plate


def _inject_notifications():
    unread_count = 0
    plates_count = 0
    try:
        conn = get_db()
        row = conn.execute("SELECT COUNT(*) FROM scraper_logs WHERE is_read = 0").fetchone()
        unread_count = row[0] if row else 0
        try:
            p_row = conn.execute("SELECT COUNT(*) FROM plate_review_queue WHERE status = 'pending'").fetchone()
            plates_count = p_row[0] if p_row else 0
        except Exception:
            plates_count = 0
    except Exception:
        pass
    return dict(unread_notifications_count=unread_count, pending_plates_count=plates_count)


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
    app.jinja_env.tests["plausible_vin"] = is_plausible_vin
    app.jinja_env.tests["valid_plate"] = is_valid_registration_plate
    app.context_processor(_inject_notifications)

    from webapp.blueprints import api, auth, cepik, dashboard, plates, review, vehicles
    for module in (auth, dashboard, vehicles, review, plates, cepik, api):
        app.register_blueprint(module.bp)

    return app
