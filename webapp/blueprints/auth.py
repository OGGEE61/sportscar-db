import hmac
import os

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

bp = Blueprint("auth", __name__)

# Endpoints called by scrapers/GitHub Actions; authenticated by API_TOKEN instead of a session
TOKEN_API_PATHS = {
    "/api/ingest", "/api/ingest_pending", "/api/mark_removed", "/api/log_run",
}


@bp.before_app_request
def require_login():
    if request.path in TOKEN_API_PATHS or request.path.startswith("/static/") or request.path == "/login":
        return
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_password and not session.get("logged_in"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        admin_password = os.environ.get("ADMIN_PASSWORD") or ""
        if admin_password and hmac.compare_digest(request.form.get("password", ""), admin_password):
            session["logged_in"] = True
            return redirect(url_for("dashboard.dashboard"))
        return render_template("login.html", error="Invalid password")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("auth.login"))
