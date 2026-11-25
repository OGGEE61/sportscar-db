import hmac
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from db import get_db

bp = Blueprint("auth", __name__)

# Endpoints called by scrapers/GitHub Actions; authenticated by API_TOKEN instead of a session
TOKEN_API_PATHS = {
    "/api/ingest", "/api/ingest_pending", "/api/mark_removed", "/api/log_run",
    "/api/known_listings", "/api/next_scrapers", "/api/reveal_queue", "/api/reveal_result",
    "/api/cepik_queue", "/api/cepik_result", "/api/plate_check_queue", "/api/plate_check_result",
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


# Wrong PINs in a row before the login locks, and for how long. The count is one for the whole
# app (login_guard), so changing address does not give a guesser more tries. A device that is
# already logged in keeps working during a lock.
MAX_FAILURES = 10
LOCK_FOR = timedelta(hours=1)


def _locked_minutes(conn) -> int:
    """Minutes left of the lock, 0 when the login is open."""
    row = conn.execute("SELECT locked_until FROM login_guard WHERE id = 1").fetchone()
    if not row or not row["locked_until"]:
        return 0
    left = datetime.fromisoformat(row["locked_until"]) - datetime.now(timezone.utc)
    return max(0, int(left.total_seconds() // 60) + 1) if left.total_seconds() > 0 else 0


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method != "POST":
        return render_template("login.html")
    conn = get_db()
    try:
        if minutes := _locked_minutes(conn):
            # The PIN is not even checked: a right guess during a lock must not get in
            return render_template("login.html", error=f"Za dużo błędnych prób. Spróbuj ponownie za {minutes} min."), 429
        admin_password = os.environ.get("ADMIN_PASSWORD") or ""
        if admin_password and hmac.compare_digest(request.form.get("password", ""), admin_password):
            conn.execute("UPDATE login_guard SET failures = 0, locked_until = NULL WHERE id = 1")
            conn.commit()
            session.permanent = True   # stays logged in on this device (PERMANENT_SESSION_LIFETIME)
            session["logged_in"] = True
            return redirect(url_for("dashboard.dashboard"))
        conn.execute("UPDATE login_guard SET failures = failures + 1 WHERE id = 1")
        failures = conn.execute("SELECT failures FROM login_guard WHERE id = 1").fetchone()["failures"]
        if failures < MAX_FAILURES:
            conn.commit()
            left = MAX_FAILURES - failures
            return render_template("login.html", error=f"Nieprawidłowy PIN. Pozostało prób: {left}.")
        until = datetime.now(timezone.utc) + LOCK_FOR
        conn.execute("UPDATE login_guard SET failures = 0, locked_until = ? WHERE id = 1", (until.isoformat(),))
        # Kept for the owner to see on /logs. The address stays in the database, out of the logs.
        conn.execute("INSERT INTO login_locks (address) VALUES (?)",
                     (request.headers.get("X-Forwarded-For", request.remote_addr),))
        conn.commit()
        print(f"[login] locked after {MAX_FAILURES} wrong PINs", flush=True)
        minutes = int(LOCK_FOR.total_seconds() // 60)
        return render_template("login.html", error=f"Za dużo błędnych prób. Logowanie zablokowane na {minutes} min."), 429
    finally:
        conn.close()


@bp.route("/logout", methods=["POST"])   # not a GET: a link or an image on another page could log the user out
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("auth.login"))
