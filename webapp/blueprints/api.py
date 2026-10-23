import hmac
import json
import os
import re

from flask import Blueprint, jsonify, request
from db import get_db, make_placeholder_vin
from webapp.model_catalog import get_model
from webapp.helpers import IS_PRODUCTION, NOW, is_plausible_vin, is_valid_registration_plate, safe_float, safe_int

from webapp.helpers import is_valid_first_registration_date
from webapp.regions import CITY_TO_REGION
from webapp.services.photos import save_photo

bp = Blueprint("api", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# REST API  (for future scrapers)
# ─────────────────────────────────────────────────────────────────────────────

def check_api_token():
    token = os.environ.get("API_TOKEN")
    if not token:
        if IS_PRODUCTION:
            return jsonify({"error": "API_TOKEN not configured"}), 503
        return None  # local dev: open
    auth = request.headers.get("Authorization", "")
    supplied = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied, token):
        return jsonify({"error": "Unauthorized"}), 401
    return None

@bp.route("/api/ingest", methods=["POST"])
def api_ingest():
    """
    Scrapers POST here. One payload = one observation row.
    If VIN is missing/invalid, a placeholder is created automatically.
    """
    if err := check_api_token(): return err
    
    p = request.get_json(force=True)
    source    = p.get("source", "api")
    source_id = p.get("source_listing_id") or p.get("source_id")
    vin = (p.get("vin") or "").strip().upper()

    # If no valid VIN, generate a placeholder
    if not vin or len(vin) != 17 or vin.startswith("UNVERIFIED"):
        if source_id:
            vin = make_placeholder_vin(source, source_id)
        else:
            return jsonify({"error": "need either valid vin or source_listing_id"}), 400

    conn = get_db()
    # Upsert vehicle (placeholder or real)
    is_placeholder = vin.startswith("UNVERIFIED")
    conn.execute("""
        INSERT INTO vehicles(vin,make,model,variant,year,body_type,
            engine_cc,engine_cyl,power_hp,drivetrain,transmission,color_ext,
            vin_status,source_method)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vin) DO UPDATE SET
            make        = CASE WHEN excluded.make  = 'Unknown' THEN make  ELSE excluded.make  END,
            model       = CASE WHEN excluded.model = 'Unknown' THEN model ELSE excluded.model END,
            variant     = COALESCE(excluded.variant, variant),
            year        = COALESCE(NULLIF(excluded.year, 0), year),
            body_type   = COALESCE(excluded.body_type, body_type),
            engine_cc   = COALESCE(excluded.engine_cc, engine_cc),
            engine_cyl  = COALESCE(excluded.engine_cyl, engine_cyl),
            power_hp    = COALESCE(excluded.power_hp, power_hp),
            drivetrain  = COALESCE(excluded.drivetrain, drivetrain),
            transmission= COALESCE(excluded.transmission, transmission),
            color_ext   = COALESCE(excluded.color_ext, color_ext),
            updated_at  = datetime('now')
    """, (
        vin,
        p.get("make","Unknown"), p.get("model","Unknown"),
        p.get("variant"), safe_int(p.get("year", 0)),
        p.get("body_type"),
        safe_int(p.get("engine_cc")), safe_int(p.get("engine_cyl")), safe_int(p.get("power_hp")),
        p.get("drivetrain"), p.get("transmission"), p.get("color_ext"),
        "placeholder" if is_placeholder else "unverified",
        f"scraper-{source}" if source in ("otomoto", "olx", "autoplac") else "api",
    ))

    c = conn.execute("""
        INSERT INTO listing_observations
          (vin,source,source_listing_id,source_url,title,price_pln,price_eur,
           mileage_km,location_city,location_region,seller_type,seller_name,
           first_seen_at,observed_at,last_seen_at,removed_at,source_method,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        vin, source, source_id,
        p.get("source_url"), p.get("title"),
        safe_float(p.get("price_pln")), safe_float(p.get("price_eur")),
        safe_int(p.get("mileage_km")),
        p.get("location_city"),
        p.get("location_region") or (CITY_TO_REGION.get(p.get("location_city")) if p.get("location_city") else None),
        p.get("seller_type"), p.get("seller_name"),
        p.get("first_seen_at") or NOW(),
        p.get("observed_at")   or NOW(),
        p.get("last_seen_at"),
        p.get("removed_at"),
        f"scraper-{source}" if source in ("otomoto", "olx", "autoplac") else "api",
        p.get("notes"),
    ))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "vin": vin, "observation_id": c.lastrowid,
                    "is_placeholder": is_placeholder})


@bp.route("/api/stats")
def api_stats():
    conn = get_db()
    data = {
        "total_vins":       conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
        "placeholder_vins": conn.execute("SELECT COUNT(*) FROM vehicles WHERE vin_status='placeholder'").fetchone()[0],
        "total_observations": conn.execute("SELECT COUNT(*) FROM listing_observations").fetchone()[0],
        "sources":          dict(conn.execute("SELECT source_method, COUNT(*) FROM listing_observations GROUP BY source_method").fetchall()),
        "schema_version":   conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
    }
    conn.close()
    return jsonify(data)

@bp.route("/api/mark_removed", methods=["POST"])
def api_mark_removed():
    """Called by scrapers after each run with the listing IDs they observed.

    Any active observation ingested by this scraper (source+make+model+variant)
    that is NOT in seen_ids gets removed_at stamped — the listing disappeared
    (likely sold). Scoping goes through the listing's own pending_listings row,
    which keeps the scraper's variant, so sibling generations sharing a model
    (M3 E46/F80, R8 V8/V10, ...) never mark each other's ads as sold.
    """
    if err := check_api_token(): return err

    p        = request.get_json(force=True)
    source   = p.get("source")
    make     = p.get("make")
    model    = p.get("model")
    variant  = p.get("variant")
    seen_ids = p.get("seen_ids", [])
    if not source or not make or not model or not variant or not seen_ids:
        # Without a variant the scope is ambiguous: refuse rather than over-mark
        return jsonify({"marked": 0, "skipped": "source, make, model, variant and seen_ids are required"})
    conn = get_db()

    # 1. Fetch active observations of listings this scraper ingested
    active_rows = conn.execute("""
        SELECT DISTINCT o.source_listing_id
        FROM listing_observations o
        JOIN pending_listings pl
          ON pl.source = o.source AND pl.source_listing_id = o.source_listing_id
        WHERE o.source = ?
          AND o.removed_at IS NULL
          AND pl.make = ? AND pl.model = ? AND pl.variant = ?
    """, (source, make, model, variant)).fetchall()
    
    seen_set = set(seen_ids)
    missing_ids = [r["source_listing_id"] for r in active_rows if r["source_listing_id"] not in seen_set]
    
    marked = 0
    if missing_ids:
        chunk_size = 50
        for i in range(0, len(missing_ids), chunk_size):
            chunk = missing_ids[i:i+chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cur = conn.execute(f"""
                UPDATE listing_observations
                SET removed_at = datetime('now'), last_seen_at = datetime('now')
                WHERE source = ?
                  AND source_listing_id IN ({placeholders})
            """, [source] + chunk)
            marked += cur.rowcount

    conn.commit()
    conn.close()
    return jsonify({"marked": marked})


@bp.route("/api/vehicles")
def api_vehicles():
    conn = get_db()
    rows = conn.execute("SELECT * FROM vehicles ORDER BY updated_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER INGEST  (scrapers POST here → pending_listing for manual review)
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/api/log_run", methods=["POST"])
def api_log_run():
    if err := check_api_token(): return err
    p = request.get_json(force=True)
    status = p.get("status", "info")
    message = p.get("message", "")
    processed = int(p.get("processed_count", 0))

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO scraper_logs (status, message, processed_count, list_url, found_count, new_count, dup_count, rej_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (status, message, processed, p.get("list_url", ""), int(p.get("found_count", 0)), int(p.get("new_count", 0)), int(p.get("dup_count", 0)), int(p.get("rej_count", 0)))
    )
    conn.commit()
    if p.get("source"):
        _set_optional_column(conn, "scraper_logs", "source", p["source"], cur.lastrowid)
    if p.get("session_status") in ("ok", "expired", "none"):
        _set_optional_column(conn, "scraper_logs", "session_status", p["session_status"], cur.lastrowid)
    conn.close()
    return jsonify({"ok": True})


def _set_optional_column(conn, table, column, value, row_id):
    """Write a column added by a recent migration; a database that hasn't run
    `python db.py` yet just skips it instead of failing the whole request."""
    try:
        conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (value, row_id))
        conn.commit()
    except Exception as e:
        print(f"[{table}.{column}] not stored (run `python db.py` to migrate): {e}")


@bp.route("/api/known_listings", methods=["POST"])
def api_known_listings():
    """Tell scrapers which listings they can skip the detail page for.

    Body: {"items": [[source, source_listing_id], ...]}
    Returns {"known": {"<source>:<id>": {"status": ..., "complete": bool}}}.
    complete = rejected, or VIN + plate + first registration already stored,
    i.e. a detail fetch could not fill anything the duplicate path would use.
    autoplac never shows a first registration date, so VIN + plate is enough there.
    """
    if err := check_api_token(): return err

    items = (request.get_json(force=True) or {}).get("items", [])[:500]
    by_source = {}
    for source, sid in items:
        if source and sid:
            by_source.setdefault(str(source), []).append(str(sid))

    known = {}
    conn = get_db()
    for source, sids in by_source.items():
        for i in range(0, len(sids), 90):  # D1 caps bound parameters at 100
            chunk = sids[i:i + 90]
            rows = conn.execute(f"""
                SELECT source_listing_id, status, vin, registration_plate, first_registration_date
                FROM pending_listings
                WHERE source = ? AND source_listing_id IN ({','.join('?' * len(chunk))})
            """, [source, *chunk]).fetchall()
            for r in rows:
                complete = r["status"] == "rejected" or bool(
                    r["vin"] and r["registration_plate"]
                    and (r["first_registration_date"] or source == "autoplac"))
                known[f"{source}:{r['source_listing_id']}"] = {"status": r["status"], "complete": complete}
    conn.close()
    return jsonify({"known": known})


@bp.route("/api/ingest_pending", methods=["POST"])
def api_ingest_pending():
    if err := check_api_token(): return err
    
    p      = request.get_json(force=True)
    source = p.get("source", "olx")
    sid    = p.get("source_listing_id")
    vin    = (p.get("vin") or "").strip().upper()
    vc     = p.get("vin_confidence", "none")

    if p.get("first_registration_date") and not is_valid_first_registration_date(p["first_registration_date"]):
        p["first_registration_date"] = None

    reg_plate = p.get("registration_plate")
    if reg_plate and not is_valid_registration_plate(reg_plate):
        reg_plate = None

    conn = get_db()
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO pending_listings
              (source, source_listing_id, source_url,
               raw_title, raw_description, photos,
               make, model, variant, year, body_type,
               engine_cc, power_hp, fuel_type,
               drivetrain, transmission, color_ext, color_int, equipment, doors,
               price_pln, price_eur, mileage_km,
               location_city, location_region,
               seller_type, seller_name,
               vin, vin_confidence,
               registration_plate, first_registration_date, origin_market,
               is_listing_active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            source, sid, p.get("source_url"),
            p.get("raw_title"), p.get("raw_description"),
            json.dumps(p.get("photos", [])),
            p.get("make"), p.get("model"), p.get("variant"),
            safe_int(p.get("year")), p.get("body_type"),
            safe_int(p.get("engine_cc")), safe_int(p.get("power_hp")), p.get("fuel_type"),
            p.get("drivetrain"), p.get("transmission"),
            p.get("color_ext"), p.get("color_int"), p.get("equipment"), safe_int(p.get("doors")),
            safe_float(p.get("price_pln")), safe_float(p.get("price_eur")), safe_int(p.get("mileage_km")),
            p.get("location_city"),
            p.get("location_region") or (CITY_TO_REGION.get(p.get("location_city")) if p.get("location_city") else None),
            p.get("seller_type"), p.get("seller_name"),
            vin or None, vc,
            reg_plate, p.get("first_registration_date"), p.get("origin_market"),
            1,
        ))
        conn.commit()

        # ── Duplicate path ────────────────────────────────────────────────────
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT * FROM pending_listings WHERE source=? AND source_listing_id=?",
                (source, sid)
            ).fetchone()
            
            if existing:
                # Update missing fields in pending_listings
                fields_to_check = [
                    "registration_plate", "first_registration_date", "body_type", 
                    "engine_cc", "power_hp", "fuel_type", "drivetrain", "transmission", 
                    "color_ext", "doors", "vin"
                ]
                updates_pending = {}
                for field in fields_to_check:
                    if not existing[field] and p.get(field):
                        val = p[field]
                        if field == "registration_plate" and not is_valid_registration_plate(val):
                            continue
                        updates_pending[field] = val
                
                if updates_pending:
                    set_clause = ", ".join(f"{k}=?" for k in updates_pending.keys())
                    vals = list(updates_pending.values()) + [existing["id"]]
                    conn.execute(f"UPDATE pending_listings SET {set_clause} WHERE id=?", vals)
                    conn.commit()

                # If it's approved and has a VIN, update the vehicles table as well
                existing_vin = existing["vin"]
                if existing_vin and existing["status"] == "approved":
                    v_existing = conn.execute("SELECT * FROM vehicles WHERE vin=?", (existing_vin,)).fetchone()
                    if v_existing:
                        v_fields = [
                            "body_type", "engine_cc", "power_hp", "drivetrain", 
                            "transmission", "color_ext", "registration_plate", 
                            "first_registration_date"
                        ]
                        updates_v = {}
                        for field in v_fields:
                            if not v_existing[field] and p.get(field):
                                updates_v[field] = p[field]
                        if updates_v:
                            set_clause = ", ".join(f"{k}=?" for k in updates_v.keys())
                            vals = list(updates_v.values()) + [existing_vin]
                            conn.execute(f"UPDATE vehicles SET {set_clause}, updated_at=datetime('now') WHERE vin=?", vals)
                            conn.commit()

            if existing and existing["status"] == "approved":
                new_price = p.get("price_pln")
                old_price = existing["price_pln"]
                existing_vin = existing["vin"]
                
                if existing_vin:
                    conn.execute("""
                        INSERT INTO listing_observations
                          (vin, source, source_listing_id, source_url, title,
                           price_pln, mileage_km, location_city,
                           seller_type, registration_plate, first_seen_at, observed_at, source_method)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        existing_vin, source, sid,
                        existing["source_url"], existing["raw_title"],
                        safe_float(new_price, safe_float(old_price, 0)),
                        p.get("mileage_km") or existing["mileage_km"],
                        p.get("location_city") or existing["location_city"],
                        existing["seller_type"] or "private",
                        p.get("registration_plate") or existing["registration_plate"],
                        NOW(), NOW(),
                        f"scraper-{source}",
                    ))
                    # Seen again: any earlier "sold" stamp on this listing was wrong
                    conn.execute(
                        "UPDATE listing_observations SET removed_at = NULL "
                        "WHERE source = ? AND source_listing_id = ? AND removed_at IS NOT NULL",
                        (source, sid))
                    conn.commit()
                    conn.close()
                    
                    # Optional: flag if price actually changed
                    tag = "price_updated" if (new_price and old_price and abs(safe_float(new_price, 0) - safe_float(old_price, 0)) > 500) else "seen_again"
                    return jsonify({"status": "ok", "id": existing["id"], "tag": tag})
            
            if existing and existing["status"] == "rejected":
                conn.close()
                return jsonify({"status": "ok", "id": existing["id"], "tag": "rejected"})

            conn.close()
            return jsonify({"status": "ok", "id": 0, "tag": "duplicate"})

        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if p.get("found_by"):
            _set_optional_column(conn, "pending_listings", "found_by", p["found_by"], lid)
        if get_model(p.get("model_id")):
            _set_optional_column(conn, "pending_listings", "model_id", p["model_id"], lid)

        # ── Download + compress photo ─────────────────────────────────────────
        photos_list = p.get("photos") or []
        photo_url   = photos_list[0] if photos_list else None
        safe_id     = re.sub(r"[^A-Za-z0-9_-]", "_", str(sid or lid))
        local_photo = save_photo(photo_url, f"{source}_{safe_id}.jpg")
        if local_photo:
            conn.execute("UPDATE pending_listings SET local_photo=? WHERE id=?",
                         (local_photo, lid))
            conn.commit()

        # ── Known VIN: already verified by a human → add observation directly ──
        # New VINs always go to the review queue regardless of VIN confidence.
        # Once a human has approved a car once, subsequent sightings are silent.
        if vin and is_plausible_vin(vin):
            known = conn.execute(
                "SELECT vin, photo FROM vehicles WHERE vin=?", (vin,)
            ).fetchone()
            if known:
                conn.execute("""
                    INSERT INTO listing_observations
                      (vin, source, source_listing_id, source_url, title,
                       price_pln, mileage_km, location_city, location_region,
                       seller_type, seller_name, registration_plate,
                       first_seen_at, observed_at, source_method)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    vin, source, sid, p.get("source_url"), p.get("raw_title"),
                    p.get("price_pln"), p.get("mileage_km"), p.get("location_city"),
                    p.get("location_region") or (CITY_TO_REGION.get(p.get("location_city")) if p.get("location_city") else None),
                    p.get("seller_type") or "private", p.get("seller_name"), p.get("registration_plate"),
                    NOW(), NOW(), f"scraper-{source}",
                ))
                
                # Update photo if it was missing
                if local_photo and (not known["photo"]):
                    conn.execute(
                        "UPDATE vehicles SET photo=? WHERE vin=?",
                        (local_photo, vin)
                    )

                # Mark the pending row as auto-approved (it's already known)
                conn.execute(
                    "UPDATE pending_listings SET status='approved', reviewed_at=datetime('now') WHERE id=?",
                    (lid,)
                )
                conn.commit()
                conn.close()
                return jsonify({"status": "ok", "id": lid, "tag": "known_vin"})

        conn.close()
        return jsonify({"status": "ok", "id": lid, "tag": "pending"})

    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500
