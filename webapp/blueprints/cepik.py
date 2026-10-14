import json
import re

from flask import Blueprint, jsonify, redirect, render_template, request
from db import get_db
from validation import is_valid_first_registration_date, is_valid_registration_plate

bp = Blueprint("cepik", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# CEPIK & HISTORIA POJAZDU (GOV.PL) DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def _fix_candidates(conn, q=""):
    """Vehicles without a CEPiK report whose plate/date need a human correction:
    CEPiK did not find them, or the stored plate/date fails validation."""
    where = ["v.vin NOT IN (SELECT vin FROM cepik_reports)",
             "(COALESCE(v.registration_plate, '') != '' OR COALESCE(v.first_registration_date, p.first_registration_date, '') != '')"]
    params = []
    if q:
        where.append("(v.vin LIKE ? OR v.registration_plate LIKE ? OR v.make LIKE ? OR v.model LIKE ?)")
        params.extend([f"%{q}%"] * 4)
    rows = conn.execute(f"""
        SELECT v.vin, v.make, v.model, v.year, v.registration_plate,
               COALESCE(v.first_registration_date, p.first_registration_date) AS first_registration_date,
               (SELECT l.status FROM cepik_sync_log l WHERE l.vin = v.vin ORDER BY l.attempted_at DESC LIMIT 1) AS last_sync_status,
               (SELECT l.message FROM cepik_sync_log l WHERE l.vin = v.vin ORDER BY l.attempted_at DESC LIMIT 1) AS last_sync_message
        FROM vehicles v
        LEFT JOIN pending_listings p ON p.vin = v.vin
        WHERE {' AND '.join(where)}
        GROUP BY v.vin
        ORDER BY v.updated_at DESC
    """, tuple(params)).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        problems = []
        if d["last_sync_status"] == "not_found":
            problems.append("CEPiK nie znalazł rekordu")
        if d["registration_plate"] and not is_valid_registration_plate(d["registration_plate"]):
            problems.append("Niepoprawna tablica")
        if d["first_registration_date"] and not is_valid_first_registration_date(d["first_registration_date"]):
            problems.append("Niepoprawna data 1. rejestracji")
        if problems:
            d["problems"] = problems
            items.append(d)
    return items


@bp.route("/cepik")
def cepik_dashboard():
    conn = get_db()
    tab = request.args.get("tab", "all")
    q = request.args.get("q", "").strip()

    # Consolidated stats
    stats_row = conn.execute("""
        SELECT 
            COUNT(*) as total_reports,
            SUM(CASE WHEN odometer_rollback = 1 THEN 1 ELSE 0 END) as rollback_count,
            SUM(CASE WHEN has_current_oc = 1 THEN 1 ELSE 0 END) as active_oc_count,
            SUM(CASE WHEN tech_inspection_status = 'Aktualne' THEN 1 ELSE 0 END) as active_skp_count,
            SUM(CASE WHEN (has_current_oc = 0 OR tech_inspection_status != 'Aktualne') THEN 1 ELSE 0 END) as issues_count,
            SUM(CASE WHEN is_stolen = 1 THEN 1 ELSE 0 END) as stolen_count
        FROM cepik_reports
    """).fetchone()

    stats = dict(stats_row) if stats_row else {
        "total_reports": 0, "rollback_count": 0, "active_oc_count": 0,
        "active_skp_count": 0, "issues_count": 0, "stolen_count": 0
    }
    for k in stats:
        stats[k] = stats[k] or 0

    stats["oc_pct"] = round((stats["active_oc_count"] / stats["total_reports"] * 100)) if stats["total_reports"] else 0
    stats["skp_pct"] = round((stats["active_skp_count"] / stats["total_reports"] * 100)) if stats["total_reports"] else 0

    missing_count = conn.execute("""
        SELECT COUNT(DISTINCT v.vin)
        FROM vehicles v
        LEFT JOIN pending_listings p ON p.vin = v.vin
        WHERE (v.registration_plate IS NOT NULL AND v.registration_plate != '')
          AND (COALESCE(v.first_registration_date, p.first_registration_date) IS NOT NULL 
               AND COALESCE(v.first_registration_date, p.first_registration_date) != '')
          AND v.vin NOT IN (SELECT vin FROM cepik_reports)
    """).fetchone()[0]

    stats["missing_count"] = missing_count
    stats["eligible_count"] = stats["total_reports"] + missing_count

    fix_items = _fix_candidates(conn, q if tab == "fix" else "")
    stats["fix_count"] = len(fix_items) if tab == "fix" and not q else len(_fix_candidates(conn, ""))

    reports = []
    missing_items = []
    sync_logs = []

    if tab in ("all", "rollback", "issues"):
        where_clauses = ["1=1"]
        params = []
        if tab == "rollback":
            where_clauses.append("c.odometer_rollback = 1")
        elif tab == "issues":
            where_clauses.append("(c.has_current_oc = 0 OR c.tech_inspection_status != 'Aktualne')")

        if q:
            where_clauses.append("(c.vin LIKE ? OR c.registration_plate LIKE ? OR c.make LIKE ? OR c.model LIKE ? OR v.make LIKE ? OR v.model LIKE ?)")
            params.extend([f"%{q}%"] * 6)

        query = f"""
            SELECT 
                c.*,
                v.make as v_make,
                v.model as v_model,
                v.year as v_year,
                v.photo as v_photo,
                (SELECT lo.price_pln FROM listing_observations lo WHERE lo.vin = c.vin ORDER BY lo.observed_at DESC, lo.id DESC LIMIT 1) as latest_price_pln,
                (SELECT lo.mileage_km FROM listing_observations lo WHERE lo.vin = c.vin ORDER BY lo.observed_at DESC, lo.id DESC LIMIT 1) as listing_mileage_km,
                (SELECT lo.source_url FROM listing_observations lo WHERE lo.vin = c.vin ORDER BY lo.observed_at DESC, lo.id DESC LIMIT 1) as source_url
            FROM cepik_reports c
            LEFT JOIN vehicles v ON v.vin = c.vin
            WHERE {' AND '.join(where_clauses)}
            ORDER BY c.odometer_rollback DESC, c.fetched_at DESC
        """
        raw_rows = conn.execute(query, tuple(params)).fetchall()
        for r in raw_rows:
            d = dict(r)
            try:
                d["odometer_history"] = json.loads(d["odometer_history_json"]) if d.get("odometer_history_json") else []
            except Exception:
                d["odometer_history"] = []
            try:
                d["events"] = json.loads(d["events_json"]) if d.get("events_json") else []
            except Exception:
                d["events"] = []
            reports.append(d)

    elif tab == "missing":
        where_clauses = [
            "(v.registration_plate IS NOT NULL AND v.registration_plate != '')",
            "(COALESCE(v.first_registration_date, p.first_registration_date) IS NOT NULL AND COALESCE(v.first_registration_date, p.first_registration_date) != '')",
            "v.vin NOT IN (SELECT vin FROM cepik_reports)"
        ]
        params = []
        if q:
            where_clauses.append("(v.vin LIKE ? OR v.registration_plate LIKE ? OR v.make LIKE ? OR v.model LIKE ?)")
            params.extend([f"%{q}%"] * 4)

        query = f"""
            SELECT 
                v.vin,
                v.make,
                v.model,
                v.year,
                v.registration_plate,
                COALESCE(v.first_registration_date, p.first_registration_date) as first_registration_date,
                v.photo,
                l.status as last_sync_status,
                l.message as last_sync_message,
                l.attempted_at as last_sync_attempt,
                (SELECT lo.price_pln FROM listing_observations lo WHERE lo.vin = v.vin ORDER BY lo.observed_at DESC, lo.id DESC LIMIT 1) as latest_price_pln,
                (SELECT lo.source_url FROM listing_observations lo WHERE lo.vin = v.vin ORDER BY lo.observed_at DESC, lo.id DESC LIMIT 1) as source_url
            FROM vehicles v
            LEFT JOIN pending_listings p ON p.vin = v.vin
            LEFT JOIN cepik_sync_log l ON l.vin = v.vin
            WHERE {' AND '.join(where_clauses)}
            GROUP BY v.vin
            ORDER BY l.attempted_at DESC NULLS LAST
            LIMIT 150
        """
        raw_rows = conn.execute(query, tuple(params)).fetchall()
        missing_items = [dict(r) for r in raw_rows]

    elif tab == "fix":
        pass  # fix_items already loaded above

    elif tab == "log":
        where_clauses = ["1=1"]
        params = []
        if q:
            where_clauses.append("(l.vin LIKE ? OR l.message LIKE ?)")
            params.extend([f"%{q}%"] * 2)

        query = f"""
            SELECT l.*, v.make, v.model, v.registration_plate
            FROM cepik_sync_log l
            LEFT JOIN vehicles v ON v.vin = l.vin
            WHERE {' AND '.join(where_clauses)}
            ORDER BY l.attempted_at DESC
            LIMIT 100
        """
        raw_rows = conn.execute(query, tuple(params)).fetchall()
        sync_logs = [dict(r) for r in raw_rows]

    conn.close()

    return render_template(
        "cepik.html",
        tab=tab,
        q=q,
        stats=stats,
        reports=reports,
        missing_items=missing_items,
        fix_items=fix_items,
        sync_logs=sync_logs,
    )


@bp.route("/corrections")
def corrections():
    return redirect("/cepik")


@bp.route("/vin-corrections")
def vin_corrections():
    conn = get_db()
    log = conn.execute(
        "SELECT * FROM vin_correction_log ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("corrections.html", log=log)


@bp.route("/api/cepik/fetch/<path:vin>", methods=["POST"])
def api_cepik_fetch_vin(vin):
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute("""
        SELECT v.vin, 
               COALESCE(v.registration_plate, p.registration_plate) as plate,
               COALESCE(v.first_registration_date, p.first_registration_date) as first_registration_date
        FROM vehicles v
        LEFT JOIN pending_listings p ON p.vin = v.vin
        WHERE v.vin = ?
        ORDER BY p.id DESC LIMIT 1
    """, (vin,)).fetchone()

    plate = (payload.get("plate") or "").strip() or (row["plate"] if row else None)
    first_reg = (payload.get("first_registration_date") or "").strip() or (row["first_registration_date"] if row else None)

    if not plate or not first_reg:
        conn.close()
        return jsonify({
            "status": "error",
            "message": "Brak numeru rejestracyjnego lub daty pierwszej rejestracji wymaganej przez CEPiK"
        }), 400

    try:
        from scripts.fetch_cepik import CepikClient, save_cepik_report
        client = CepikClient()
        report = client.fetch_vehicle_data(vin, plate, first_reg)
        if not report:
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Serwer CEPiK nie odnalazł rekordu (sprawdź zgodność tablicy i daty pierwszej rejestracji)"
            }), 404

        save_cepik_report(report, conn)
        conn.close()
        return jsonify({"status": "ok", "report": report})
    except Exception as e:
        conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/api/cepik/fix/<path:vin>", methods=["POST"])
def api_cepik_fix_vin(vin):
    """Store a human-corrected plate / first registration date on the vehicle."""
    payload = request.get_json(silent=True) or {}
    plate = re.sub(r"[\s\-\.]", "", (payload.get("plate") or "")).upper()
    first_reg = (payload.get("first_registration_date") or "").strip()
    if not is_valid_registration_plate(plate):
        return jsonify({"status": "error", "message": "Niepoprawny numer rejestracyjny"}), 400
    if not is_valid_first_registration_date(first_reg):
        return jsonify({"status": "error", "message": "Niepoprawna data (RRRR-MM-DD, od 1980, nie z przyszłości)"}), 400
    conn = get_db()
    cur = conn.execute(
        "UPDATE vehicles SET registration_plate=?, first_registration_date=?, updated_at=datetime('now') WHERE vin=?",
        (plate, first_reg, vin))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"status": "error", "message": "Nie znaleziono pojazdu"}), 404
    return jsonify({"status": "ok", "plate": plate, "first_registration_date": first_reg})
