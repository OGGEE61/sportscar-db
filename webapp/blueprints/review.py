import json

from flask import Blueprint, flash, redirect, render_template, request, url_for
from db import get_db, make_placeholder_vin
from webapp.helpers import is_plausible_vin
from webapp.services.listings import _approve_listing

bp = Blueprint("review", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# REVIEW QUEUE
# ─────────────────────────────────────────────────────────────────────────────

REVIEW_PER_PAGE = 30


@bp.route("/review")
def review_queue():
    status_filter = request.args.get("status", "pending")
    source = request.args.get("source", "")
    source = source if source in ("olx", "otomoto") else ""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    src_sql, src_params = (" AND source = ?", [source]) if source else ("", [])
    conn = get_db()
    counts = {r["status"]: r["cnt"] for r in conn.execute(f"""
        SELECT status, COUNT(*) AS cnt FROM pending_listings WHERE 1=1{src_sql} GROUP BY status
    """, src_params).fetchall()}
    pages = max((counts.get(status_filter, 0) + REVIEW_PER_PAGE - 1) // REVIEW_PER_PAGE, 1)
    page = min(page, pages)
    order_col = "reviewed_at" if status_filter == "approved" else "scraped_at"
    listings = conn.execute(f"""
        SELECT * FROM pending_listings
        WHERE status = ?{src_sql}
        ORDER BY {order_col} DESC
        LIMIT ? OFFSET ?
    """, (status_filter, *src_params, REVIEW_PER_PAGE, (page - 1) * REVIEW_PER_PAGE)).fetchall()
    conn.close()
    return render_template("review.html",
        listings=listings, counts=counts, status_filter=status_filter,
        source=source, page=page, pages=pages)


@bp.route("/review/<int:pid>")
def review_detail(pid):
    conn = get_db()
    listing = conn.execute(
        "SELECT * FROM pending_listings WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not listing:
        return "Not found", 404
    photos = json.loads(listing["photos"]) if listing["photos"] else []
    equipment = json.loads(listing["equipment"]) if listing["equipment"] else []
    ai_equipment = []
    if listing["ai_equipment"]:
        try:
            ai_equipment = json.loads(listing["ai_equipment"]) if isinstance(listing["ai_equipment"], str) else listing["ai_equipment"]
        except Exception:
            ai_equipment = []
    return render_template("review_detail.html", listing=listing, photos=photos, equipment=equipment, ai_equipment=ai_equipment)


@bp.route("/review/<int:pid>/approve", methods=["POST"])
def review_approve(pid):
    conn = get_db()
    listing = conn.execute(
        "SELECT * FROM pending_listings WHERE id=?", (pid,)).fetchone()
    if not listing:
        conn.close()
        return "Not found", 404
    try:
        _approve_listing(conn, listing, overrides=dict(request.form))
        conn.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        conn.close()
        return f"Error approving listing: {e}", 500

    conn.close()
    if request.args.get("ajax") == "1":
        return {"status": "success", "id": pid}

    # Auto-advance to next pending
    conn = get_db()
    next_p = conn.execute(
        "SELECT id FROM pending_listings WHERE status='pending' ORDER BY scraped_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if next_p:
        return redirect(url_for("review.review_detail", pid=next_p["id"]))
    return redirect(url_for("review.review_queue"))

@bp.route("/review/reject_all_pending", methods=["POST"])
def review_reject_all_pending():
    conn = get_db()
    conn.execute(
        "UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') WHERE status='pending'"
    )
    conn.commit()
    conn.close()
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review.review_queue"))

@bp.route("/review/clear_rejected", methods=["POST"])
def review_clear_rejected():
    conn = get_db()
    conn.execute("DELETE FROM pending_listings WHERE status='rejected'")
    conn.commit()
    conn.close()
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review.review_queue"))


@bp.route("/review/bulk_approve", methods=["POST"])
def review_bulk_approve():
    ids = request.form.getlist("ids")
    if ids:
        conn = get_db()
        for pid in ids:
            listing = conn.execute(
                "SELECT * FROM pending_listings WHERE id=? AND status='pending'", (pid,)
            ).fetchone()
            if not listing:
                continue
            try:
                _approve_listing(conn, listing)
            except Exception as e:
                print(f"Bulk approve error for id {pid}: {e}")
        conn.commit()
        conn.close()
    
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review.review_queue"))


@bp.route("/review/bulk_reject_novin", methods=["POST"])
def review_bulk_reject_novin():
    conn = get_db()
    pending = conn.execute("SELECT id, vin FROM pending_listings WHERE status='pending'").fetchall()
    count = 0
    for p in pending:
        if not is_plausible_vin(p["vin"]):
            conn.execute("UPDATE pending_listings SET status='rejected', review_notes='Missing/Invalid VIN' WHERE id=?", (p["id"],))
            count += 1
    conn.commit()
    conn.close()
    flash(f"Automatically rejected {count} listings with missing or invalid VINs.", "success")
    return redirect(url_for("review.review_queue"))


@bp.route("/review/bulk_reject_approved_novin", methods=["POST"])
def review_bulk_reject_approved_novin():
    conn = get_db()
    approved = conn.execute("SELECT id, vin, source, source_listing_id FROM pending_listings WHERE status='approved'").fetchall()
    count = 0
    for p in approved:
        if not is_plausible_vin(p["vin"]):
            # Also clean up the vehicle profile that got created using the placeholder VIN
            placeholder = make_placeholder_vin(p["source"] or "olx", p["source_listing_id"] or str(p["id"]))
            conn.execute("DELETE FROM vehicles WHERE vin=?", (placeholder,))
            
            conn.execute("UPDATE pending_listings SET status='rejected', review_notes='Missing/Invalid VIN - Retroactively Rejected' WHERE id=?", (p["id"],))
            count += 1
    conn.commit()
    conn.close()
    flash(f"Retroactively rejected {count} approved listings with missing/invalid VINs and removed their vehicle profiles.", "success")
    return redirect(url_for("review.review_queue", status="approved"))


@bp.route("/review/bulk_reject", methods=["POST"])
def review_bulk_reject():
    ids = request.form.getlist("ids")
    if ids:
        conn = get_db()
        conn.execute(
            f"UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') "
            f"WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        conn.commit()
        conn.close()
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review.review_queue"))


@bp.route("/review/<int:pid>/reject", methods=["POST"])
def review_reject(pid):
    reason = request.form.get("reason", "")
    conn = get_db()
    conn.execute("""
        UPDATE pending_listings
        SET status='rejected', reviewed_at=datetime('now'), review_notes=?
        WHERE id=?
    """, (reason, pid))
    conn.commit()
    
    if request.args.get("ajax") == "1":
        conn.close()
        return {"status": "success", "id": pid}

    # Auto-advance to next pending
    next_p = conn.execute(
        "SELECT id FROM pending_listings WHERE status='pending' ORDER BY scraped_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if next_p:
        return redirect(url_for("review.review_detail", pid=next_p["id"]))
    return redirect(url_for("review.review_queue"))
