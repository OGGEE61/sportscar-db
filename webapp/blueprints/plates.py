import re

from flask import Blueprint, jsonify, render_template, request
from db import get_db
from webapp import invalidate_notifications
from webapp.services.plates import allow_cepik_retry, clear_plate

bp = Blueprint("plates", __name__)


@bp.after_request
def _refresh_badge(resp):
    # Reviews/scans change the pending-plates count shown in the navbar
    if request.method == "POST":
        invalidate_notifications()
    return resp


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
               p.price_pln, p.location_city, p.raw_title
        FROM plate_review_queue q
        LEFT JOIN vehicles v ON v.vin = q.vin
        LEFT JOIN pending_listings p ON (p.id = q.listing_id OR (q.listing_id IS NULL AND p.vin = q.vin))
        WHERE q.status = ?
          AND q.vin IS NOT NULL 
          AND q.vin != '' 
          AND q.vin NOT LIKE 'PLH%'
          AND (p.status IS NULL OR p.status != 'rejected')
        GROUP BY q.id
        ORDER BY COALESCE(q.reviewed_at, q.created_at) DESC, q.id DESC
    """, (status_filter,)).fetchall()

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
        final_plate = plate or cand["detected_plate"]
        clean_plate = re.sub(r"[^A-Z0-9]", "", (final_plate or "").upper())
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

        conn.execute("""
            UPDATE plate_review_queue
            SET status='approved', reviewed_plate=?, reviewed_at=datetime('now')
            WHERE id=?
        """, (final_plate, cid))

        if lid:
            conn.execute("UPDATE pending_listings SET registration_plate=? WHERE id=?", (final_plate, lid))
        if vin:
            conn.execute("UPDATE pending_listings SET registration_plate=? WHERE vin=?", (final_plate, vin))
            conn.execute("""
                UPDATE vehicles 
                SET registration_plate=?, 
                    vin_status = CASE WHEN vin LIKE 'UNVERIFIED%' THEN 'placeholder' ELSE 'verified' END 
                WHERE vin=?
            """, (final_plate, vin))
            conn.execute("UPDATE listing_observations SET registration_plate=? WHERE vin=?", (final_plate, vin))
            try:
                conn.execute("DELETE FROM tags WHERE vin=? AND tag IN ('missing plates', 'Missing plates')", (vin,))
                conn.execute("INSERT OR IGNORE INTO tags (vin, tag, source_method) VALUES (?, 'photo extracted', 'photo-extracted')", (vin,))
            except Exception:
                pass
        if vin:
            allow_cepik_retry(conn, vin, final_plate)
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "id": cid, "action": action, "plate": final_plate})

    elif action == "reject":
        conn.execute("""
            UPDATE plate_review_queue
            SET status='rejected', reviewed_at=datetime('now')
            WHERE id=?
        """, (cid,))

        if prev_status == "approved":
            clear_plate(conn, vin, lid, old_plate)
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "id": cid, "action": action})

    elif action == "revert":
        conn.execute("""
            UPDATE plate_review_queue
            SET status='pending', reviewed_plate=NULL, reviewed_at=NULL
            WHERE id=?
        """, (cid,))

        if prev_status == "approved":
            clear_plate(conn, vin, lid, old_plate)
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
