import json
import re

from flask import Blueprint, jsonify, render_template, request
from db import get_db
from webapp import invalidate_notifications
from webapp.services.plates import approve_plate, clear_plate, normalize_plate, restore_plate

bp = Blueprint("plates", __name__)


@bp.after_request
def _refresh_badge(resp):
    # Reviews/scans change the pending-plates count shown in the navbar
    if request.method == "POST":
        invalidate_notifications()
    return resp


def _photo_list(photos_json):
    try:
        photos = json.loads(photos_json or "[]")
    except (ValueError, TypeError):
        return []
    return photos if isinstance(photos, list) else []


# ── Plates Review (Human-in-the-Loop for CV License Plate Recognition) ───────

@bp.route("/plates")
def plates_review():
    conn = get_db()
    status_filter = request.args.get("status", "pending")
    if status_filter not in ("pending", "approved", "rejected"):
        status_filter = "pending"
    
    # Ensure table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plate_review_queue (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id          TEXT,
            vin                 TEXT,
            source_url          TEXT,
            photo_url           TEXT,
            crop_path           TEXT,
            detected_plate      TEXT,
            confidence          REAL,
            status              TEXT NOT NULL DEFAULT 'pending',
            reviewed_plate      TEXT,
            reviewed_at         TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    candidates = conn.execute("""
        SELECT q.id, q.listing_id, q.vin, q.source_url, q.photo_url, q.crop_path, 
               q.detected_plate, q.confidence, q.status, q.reviewed_plate, q.reviewed_at, q.created_at,
               COALESCE(v.make, p.make) as make,
               COALESCE(v.model, p.model) as model,
               COALESCE(v.variant, p.variant) as variant,
               COALESCE(v.year, p.year) as year,
               p.price_pln, p.location_city, p.raw_title,
               v.registration_plate AS car_plate,
               COALESCE(NULLIF(v.first_registration_date, ''), p.first_registration_date) AS first_reg,
               p.photos AS photos_json,
               p.source AS listing_source
        FROM plate_review_queue q
        LEFT JOIN vehicles v ON v.vin = q.vin
        -- The queue entry's listing, else the newest listing of its VIN. An OR in the join made
        -- SQLite scan every listing for every entry (hundreds of thousands of rows a page).
        LEFT JOIN pending_listings p ON p.id = COALESCE(q.listing_id,
            (SELECT p2.id FROM pending_listings p2 WHERE p2.vin = q.vin ORDER BY p2.id DESC LIMIT 1))
        WHERE q.status = ?
          AND q.vin IS NOT NULL 
          AND q.vin != '' 
          AND q.vin NOT LIKE 'PLH%'
          AND (p.status IS NULL OR p.status != 'rejected')
        GROUP BY q.id
        ORDER BY COALESCE(q.reviewed_at, q.created_at) DESC, q.id DESC
    """, (status_filter,)).fetchall()
    candidates = [{**dict(c), "photos": _photo_list(c["photos_json"])} for c in candidates]

    stats = {
        "pending": conn.execute("""
            SELECT COUNT(DISTINCT q.id) FROM plate_review_queue q
            LEFT JOIN pending_listings p ON p.id = q.listing_id
            WHERE q.status='pending' 
              AND q.vin IS NOT NULL AND q.vin != '' AND q.vin NOT LIKE 'PLH%'
              AND (p.status IS NULL OR p.status != 'rejected')
        """).fetchone()[0],
        "approved": conn.execute("""
            SELECT COUNT(DISTINCT q.id) FROM plate_review_queue q
            LEFT JOIN pending_listings p ON p.id = q.listing_id
            WHERE q.status='approved'
              AND q.vin IS NOT NULL AND q.vin != '' AND q.vin NOT LIKE 'PLH%'
              AND (p.status IS NULL OR p.status != 'rejected')
        """).fetchone()[0],
        "rejected": conn.execute("""
            SELECT COUNT(DISTINCT q.id) FROM plate_review_queue q
            LEFT JOIN pending_listings p ON p.id = q.listing_id
            WHERE q.status='rejected'
              AND q.vin IS NOT NULL AND q.vin != '' AND q.vin NOT LIKE 'PLH%'
              AND (p.status IS NULL OR p.status != 'rejected')
        """).fetchone()[0],
        "missing_plates": conn.execute("""
            SELECT COUNT(*) FROM pending_listings 
            WHERE (registration_plate IS NULL OR registration_plate='') 
              AND status != 'rejected'
              AND vin IS NOT NULL AND vin != '' AND vin NOT LIKE 'PLH%'
              AND photos IS NOT NULL AND photos != '[]'
        """).fetchone()[0],
    }
    conn.close()
    return render_template("plates.html", candidates=candidates, stats=stats, status_filter=status_filter)


@bp.route("/api/plates/review", methods=["POST"])
def api_plates_review():
    data = request.get_json(silent=True) or request.form
    cid = data.get("id")
    action = data.get("action")  # 'approve', 'reject', or 'revert'
    plate = (data.get("plate") or "").strip().upper()

    if not cid or action not in ("approve", "reject", "revert"):
        return jsonify({"status": "error", "message": "Niepoprawne parametry"}), 400

    conn = get_db()
    cand = conn.execute("SELECT * FROM plate_review_queue WHERE id=?", (cid,)).fetchone()
    if not cand:
        conn.close()
        return jsonify({"status": "error", "message": "Nie znaleziono pozycji"}), 404

    vin = cand["vin"]
    lid = cand["listing_id"]
    prev_status = cand["status"]
    old_plate = cand["reviewed_plate"] or cand["detected_plate"]

    if action == "approve":
        raw_plate = (plate or cand["detected_plate"] or "").upper()
        # Separators are dropped; any other symbol (e.g. a Polish letter) would silently change the plate
        if re.search(r"[^A-Z0-9\s\-.]", raw_plate):
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Tablica może zawierać tylko litery A-Z i cyfry."
            }), 400
        final_plate = normalize_plate(raw_plate)
        clean_plate = final_plate
        if len(clean_plate) < 3:
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Tablica rejestracyjna musi mieć co najmniej 3 znaki."
            }), 400
        if len(clean_plate) > 8 and not data.get("force"):
            conn.close()
            return jsonify({
                "status": "needs_confirmation",
                "message": f"Wpisany numer ma {len(clean_plate)} znaków (w Polsce standard to max 8). Jeśli na pewno chcesz zatwierdzić w tej formie, potwierdź."
            }), 400

        approve_plate(conn, cid, vin, lid, final_plate)
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "id": cid, "action": action, "plate": final_plate})

    elif action == "reject":
        # The number is missing or wrong, so the car must not keep it. Remembering it in
        # reviewed_plate allows undo and stops the next scrape of the listing from putting
        # it back (see /api/ingest_pending).
        row = conn.execute("SELECT registration_plate FROM vehicles WHERE vin=?", (vin,)).fetchone()
        removed = normalize_plate(row["registration_plate"] if row else None) or None
        conn.execute("""
            UPDATE plate_review_queue
            SET status='rejected', reviewed_plate=?, reviewed_at=datetime('now')
            WHERE id=?
        """, (removed, cid))
        clear_plate(conn, vin, lid, removed)
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "id": cid, "action": action, "removed": removed})

    elif action == "revert":
        conn.execute("""
            UPDATE plate_review_queue
            SET status='pending', reviewed_plate=NULL, reviewed_at=NULL
            WHERE id=?
        """, (cid,))

        if prev_status == "approved":
            clear_plate(conn, vin, lid, old_plate)
        elif prev_status == "rejected" and cand["reviewed_plate"]:
            restore_plate(conn, vin, cand["reviewed_plate"])
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "id": cid, "action": action})


@bp.route("/api/plates/scan_batch", methods=["POST"])
def api_plates_scan_batch():
    limit = int(request.args.get("limit") or 5)
    rescan = request.args.get("rescan", "0") in ("1", "true", "True")
    try:
        from scripts.detect_plates import run_plate_detection_batch
        res = run_plate_detection_batch(limit=limit, rescan_empty=rescan)
        return jsonify({"status": "ok", "scanned": res["scanned_count"], "found": res["found_plates"]})
    except ImportError:
        return jsonify({
            "status": "error",
            "message": "Skanowanie CV za pomocą YOLOv8/EasyOCR uruchamia się lokalnie na Twoim komputerze (skrypt scripts/detect_plates.py), ponieważ silnik CV wymaga bibliotek PyTorch."
        }), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
