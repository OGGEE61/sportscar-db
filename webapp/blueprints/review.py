import json

from flask import Blueprint, flash, redirect, render_template, request, url_for
from db import get_db, make_placeholder_vin
from webapp.helpers import damage_reason_sql, is_plausible_vin
from webapp.services import verification
from webapp.services.listings import _approve_listing
from validation import MARKETS, ORIGIN_UNKNOWN

bp = Blueprint("review", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# REVIEW QUEUE
# ─────────────────────────────────────────────────────────────────────────────

REVIEW_PER_PAGE = 30


def _source_scope(column="source"):
    """SQL fragment + params limiting a mass action to the source filter
    the user is looking at (?source=...). Empty when no filter is active."""
    source = request.args.get("source", "")
    if source in ("olx", "otomoto", "autoplac"):
        return f" AND {column} = ?", [source]
    return "", []


@bp.route("/review")
def review_queue():
    status_filter = request.args.get("status", "pending")
    source = request.args.get("source", "")
    source = source if source in ("olx", "otomoto", "autoplac") else ""
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
        SELECT *, {damage_reason_sql("pending_listings")} AS damage FROM pending_listings
        WHERE status = ?{src_sql}
        ORDER BY {order_col} DESC
        LIMIT ? OFFSET ?
    """, (status_filter, *src_params, REVIEW_PER_PAGE, (page - 1) * REVIEW_PER_PAGE)).fetchall()
    origin_conflicts = _origin_conflict_count(conn)
    conn.close()
    return render_template("review.html",
        listings=listings, counts=counts, status_filter=status_filter,
        source=source, page=page, pages=pages, origin_conflicts=origin_conflicts)


# ─────────────────────────────────────────────────────────────────────────────
# ORIGIN REVIEW: cars whose stored origin market and Bielik's disagree
# ─────────────────────────────────────────────────────────────────────────────



def _origin_conflict_count(conn):
    return conn.execute("SELECT COUNT(*) FROM vehicles WHERE ai_conflict = 1").fetchone()[0]


def origin_conflicts(conn):
    """The cars where Bielik and the stored origin market disagree, by make and model, and each car's
    live ads (pending or approved, newest first). Also used by the review MCP server (scripts/review_mcp.py)."""
    # Both queries read only the flagged cars through idx_vehicles_ai_conflict and idx_pending_vin.
    # Sorting and the status filter are done here: in SQL the planner takes the make/model and
    # status indexes instead, which read the whole tables.
    cars = sorted(conn.execute("""
        SELECT car_id, vin, make, model, variant, year, origin_market, ai_suggested_market, ai_reasoning, ai_ad_count
        FROM vehicles WHERE ai_conflict = 1
    """).fetchall(), key=lambda c: (c["make"] or "", c["model"] or "", c["vin"]))
    ads = {}
    for ad in conn.execute("""
        SELECT vin, source, source_url, scraped_at, status FROM pending_listings
        WHERE vin IN (SELECT vin FROM vehicles WHERE ai_conflict = 1)
    """):
        if ad["status"] in ("approved", "pending"):
            ads.setdefault(ad["vin"], []).append(ad)
    for car_ads in ads.values():
        car_ads.sort(key=lambda a: a["scraped_at"] or "", reverse=True)
    return cars, ads


def decide_origin(conn, vin, market):
    """Store the car's origin market as decided: one of MARKETS, the stored one, or "nieznany". It is
    kept from then on: scraping does not overwrite it and Bielik does not flag the car again. Agreeing
    with Bielik also takes his interior colour, held back over the conflict. Returns an error message
    and HTTP status, or (None, 200)."""
    car = conn.execute("SELECT origin_market FROM vehicles WHERE vin = ?", (vin,)).fetchone()
    if not car:
        return "Nie znaleziono auta", 404
    if market not in MARKETS and market != ORIGIN_UNKNOWN and market != car["origin_market"]:
        return "Nieznany rynek", 400
    chosen = None if market == ORIGIN_UNKNOWN else market
    conn.execute("""
        UPDATE vehicles
        SET origin_market = ?, origin_checked_at = CURRENT_TIMESTAMP, ai_conflict = 0, updated_at = CURRENT_TIMESTAMP,
            color_int = CASE WHEN ? = ai_suggested_market THEN COALESCE(color_int, ai_interior_color) ELSE color_int END
        WHERE vin = ?
    """, (chosen, chosen, vin))
    conn.commit()
    return None, 200


@bp.route("/review/origins")
def review_origins():
    conn = get_db()
    cars, ads = origin_conflicts(conn)
    notes_open = verification.open_note_count(conn)
    conn.close()
    return render_template("review_origins.html", cars=cars, ads=ads, markets=MARKETS, unknown=ORIGIN_UNKNOWN,
                           notes_open=notes_open)


@bp.route("/review/origins/<vin>", methods=["POST"])
def review_origin_decide(vin):
    """Form field market: the car's origin market as decided (see decide_origin)."""
    market = request.form.get("market", "")
    conn = get_db()
    error, status = decide_origin(conn, vin, market)
    left = _origin_conflict_count(conn) if not error else None
    conn.close()
    if error:
        return error, status
    if request.headers.get("HX-Request"):
        # The card is swapped out; the counter is updated out of band
        return f'<span class="badge bg-warning text-dark" id="origin-conflict-count" hx-swap-oob="true">{left}</span>'
    flash(f"Zapisano rynek: {market}.", "success")
    return redirect(url_for("review.review_origins"))


@bp.route("/review/notes")
def review_notes():
    """"Do sprawdzenia": cars a review left uncertain (?status=resolved: the latest ticked off). Its
    other tab is the origin conflicts (/review/origins)."""
    resolved = request.args.get("status") == "resolved"
    conn = get_db()
    notes = verification.review_notes(conn, resolved=resolved)
    notes_open = len(notes) if not resolved else verification.open_note_count(conn)
    origins = _origin_conflict_count(conn)
    conn.close()
    return render_template("review_notes.html", notes=notes, resolved=resolved, topics=verification.NOTE_TOPICS,
                           notes_open=notes_open, origin_conflicts=origins)


@bp.route("/review/notes/<int:note_id>", methods=["POST"])
def review_note_resolve(note_id):
    """Form field resolved=1: the note is checked and leaves the list; 0 puts it back."""
    conn = get_db()
    error = verification.set_note_resolved(conn, note_id, request.form.get("resolved") == "1")
    conn.close()
    if error:
        return error, 409
    if request.headers.get("HX-Request"):
        return ""   # the card is swapped out
    return redirect(url_for("review.review_notes"))


@bp.route("/review/<int:pid>")
def review_detail(pid):
    conn = get_db()
    listing = conn.execute(
        f"SELECT *, {damage_reason_sql('pending_listings')} AS damage FROM pending_listings WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not listing:
        return "Nie znaleziono ogłoszenia", 404
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
        f"SELECT *, {damage_reason_sql('pending_listings')} AS damage FROM pending_listings WHERE id=?", (pid,)).fetchone()
    if not listing:
        conn.close()
        return "Nie znaleziono ogłoszenia", 404
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
    src_sql, src_params = _source_scope()
    conn = get_db()
    # Listings whose VIN waits behind "Show VIN" stay: rejecting them would lose the car for good
    conn.execute(
        f"UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') WHERE status='pending'{src_sql} "
        f"AND NOT ({AWAITS_REVEAL_SQL})",
        src_params,
    )
    skipped = conn.execute(f"SELECT COUNT(*) FROM pending_listings WHERE status='pending'{src_sql} AND {AWAITS_REVEAL_SQL}",
                           src_params).fetchone()[0]
    conn.commit()
    conn.close()
    _flash_skipped(skipped)
    if request.args.get("ajax") == "1":
        return {"status": "success", "skipped": skipped}
    return redirect(url_for("review.review_queue"))

@bp.route("/review/clear_rejected", methods=["POST"])
def review_clear_rejected():
    src_sql, src_params = _source_scope()
    conn = get_db()
    conn.execute(f"DELETE FROM pending_listings WHERE status='rejected'{src_sql}", src_params)
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


@bp.route("/review/pending_with_vin")
def review_pending_with_vin():
    """Ids of pending listings with a plausible VIN, for "Approve all with VIN".

    The counterpart of bulk_reject_novin (same check, same source filter). The page approves them
    one by one through review_approve, as "Approve selected" does, so no request runs long.
    """
    src_sql, src_params = _source_scope()
    conn = get_db()
    pending = conn.execute(
        f"SELECT id, vin FROM pending_listings WHERE status='pending'{src_sql} ORDER BY scraped_at DESC",
        src_params).fetchall()
    conn.close()
    return {"ids": [p["id"] for p in pending if is_plausible_vin(p["vin"])]}


def vin_awaits_reveal(listing) -> bool:
    """True for an otomoto ad whose VIN sits behind "Show VIN" and was not revealed yet.

    Such a listing has a VIN; the reveal job fills it in (scripts/maintenance/reveal_pending_vins.py).
    Rejecting it would lose the car for good: the scrapers never look at a rejected listing again.
    """
    return (listing["source"] == "otomoto" and listing["vin_confidence"] == "found_in_schema"
            and not (listing["vin"] or "").strip())


# SQL twin of vin_awaits_reveal(): an Otomoto listing whose VIN is behind "Show VIN" and not revealed yet
AWAITS_REVEAL_SQL = ("source = 'otomoto' AND vin_confidence = 'found_in_schema' "
                     "AND COALESCE(TRIM(vin), '') = ''")


def _flash_skipped(skipped):
    if skipped:
        flash(f"Pominięto {skipped}: VIN jest w ogłoszeniu za „Pokaż VIN” i czeka na odsłonięcie. "
              "Te ogłoszenia zostają w Kolejce.", "warning")


@bp.route("/review/bulk_reject_novin", methods=["POST"])
def review_bulk_reject_novin():
    src_sql, src_params = _source_scope()
    conn = get_db()
    pending = conn.execute(
        f"SELECT id, vin, source, vin_confidence FROM pending_listings WHERE status='pending'{src_sql}",
        src_params).fetchall()
    count = waiting = 0
    for p in pending:
        if is_plausible_vin(p["vin"]):
            continue
        if vin_awaits_reveal(p):
            waiting += 1
            continue
        conn.execute("UPDATE pending_listings SET status='rejected', review_notes='Missing/Invalid VIN' WHERE id=?", (p["id"],))
        count += 1
    conn.commit()
    conn.close()
    flash(f"Odrzucono {count} ogłoszeń bez VIN-u lub z błędnym VIN-em."
          + (f" Pominięto {waiting}: VIN jest w ogłoszeniu za „Pokaż VIN” i czeka na odsłonięcie." if waiting else ""),
          "success")
    return redirect(url_for("review.review_queue", source=request.args.get("source") or None))


@bp.route("/review/bulk_reject_approved_novin", methods=["POST"])
def review_bulk_reject_approved_novin():
    src_sql, src_params = _source_scope()
    conn = get_db()
    approved = conn.execute(
        f"SELECT id, vin, source, source_listing_id FROM pending_listings WHERE status='approved'{src_sql}",
        src_params).fetchall()
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
    flash(f"Odrzucono {count} zatwierdzonych ogłoszeń bez poprawnego VIN-u i usunięto profile ich aut.", "success")
    return redirect(url_for("review.review_queue", status="approved", source=request.args.get("source") or None))


@bp.route("/review/bulk_reject", methods=["POST"])
def review_bulk_reject():
    ids = request.form.getlist("ids")
    skipped = 0
    if ids:
        conn = get_db()
        marks = ",".join("?" * len(ids))
        skipped = conn.execute(f"SELECT COUNT(*) FROM pending_listings WHERE id IN ({marks}) AND {AWAITS_REVEAL_SQL}",
                               ids).fetchone()[0]
        conn.execute(
            f"UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') "
            f"WHERE id IN ({marks}) AND NOT ({AWAITS_REVEAL_SQL})",
            ids,
        )
        conn.commit()
        conn.close()
    _flash_skipped(skipped)
    if request.args.get("ajax") == "1":
        return {"status": "success", "skipped": skipped}
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
