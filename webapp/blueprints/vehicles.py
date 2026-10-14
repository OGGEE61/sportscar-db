import json
from datetime import datetime
from flask import Blueprint, redirect, render_template, request, url_for
from db import get_db, resolve_placeholder
from webapp.helpers import NOW, safe_float, safe_int
from webapp.regions import CITY_TO_REGION, REGION_NAMES

bp = Blueprint("vehicles", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# VEHICLES LIST
# ─────────────────────────────────────────────────────────────────────────────

PER_PAGE = 50


@bp.route("/vehicles")
def vehicles_list():
    conn   = get_db()
    q      = request.args.get("q", "").strip()
    make   = request.args.get("make", "")
    status = request.args.get("status", "")
    region = request.args.get("region", "").strip()
    source = request.args.get("source", "")
    source = source if source in ("olx", "otomoto") else ""
    sort   = request.args.get("sort", "last_seen")
    page   = max(request.args.get("page", 1, type=int) or 1, 1)

    # Pre-aggregate per VIN (avoids the observations x tags row fan-out)
    base = """
        SELECT v.*, o.obs_count, o.ad_count, o.min_price, o.max_price,
               o.last_observed, o.active_ads, o.sources, t.tags
        FROM vehicles v
        LEFT JOIN (
            SELECT vin,
                   COUNT(*)                          AS obs_count,
                   COUNT(DISTINCT source_listing_id) AS ad_count,
                   MIN(price_pln)                    AS min_price,
                   MAX(price_pln)                    AS max_price,
                   MAX(observed_at)                  AS last_observed,
                   SUM(CASE WHEN removed_at IS NULL THEN 1 ELSE 0 END) AS active_ads,
                   GROUP_CONCAT(DISTINCT source)     AS sources
            FROM listing_observations GROUP BY vin
        ) o ON o.vin = v.vin
        LEFT JOIN (
            SELECT vin, GROUP_CONCAT(tag) AS tags FROM tags GROUP BY vin
        ) t ON t.vin = v.vin
    """
    wheres, params = [], []
    if q:
        wheres.append("(v.make LIKE ? OR v.model LIKE ? OR v.vin LIKE ? OR v.variant LIKE ?)")
        params += [f"%{q}%"] * 4
    if make:
        wheres.append("v.make = ?"); params.append(make)
    if status:
        wheres.append("v.vin_status = ?"); params.append(status)
    if source:
        wheres.append("v.vin IN (SELECT vin FROM listing_observations WHERE source = ?)"); params.append(source)
    if region:
        cities_in_region = [c for c, r in CITY_TO_REGION.items() if r == region]
        cond = "lo.location_region = ?"
        rparams = [region]
        if cities_in_region:
            cond += f" OR lo.location_city IN ({','.join('?' for _ in cities_in_region)})"
            rparams += cities_in_region
        wheres.append(f"v.vin IN (SELECT lo.vin FROM listing_observations lo WHERE {cond})")
        params += rparams

    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""

    sort_map = {
        "last_seen":  "o.last_observed DESC, v.updated_at DESC",
        "updated_at": "v.updated_at DESC",
        "year_desc":  "v.year DESC",
        "year_asc":   "v.year ASC",
        "power":      "v.power_hp DESC",
        "obs":        "o.obs_count DESC",
        "price":      "o.min_price ASC NULLS LAST",
    }
    order_sql = " ORDER BY " + sort_map.get(sort, sort_map["last_seen"])

    total = conn.execute(f"SELECT COUNT(*) FROM vehicles v{where_sql}", params).fetchone()[0]
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(page, pages)
    vehicles = conn.execute(
        base + where_sql + order_sql + " LIMIT ? OFFSET ?",
        [*params, PER_PAGE, (page - 1) * PER_PAGE],
    ).fetchall()
    makes    = conn.execute("SELECT DISTINCT make FROM vehicles ORDER BY make").fetchall()
    conn.close()
    return render_template("vehicles.html",
        vehicles=vehicles, makes=[m["make"] for m in makes],
        q=q, selected_make=make, status=status, sort=sort,
        selected_region=region, regions=REGION_NAMES, source=source,
        page=page, pages=pages, total=total)


# ─────────────────────────────────────────────────────────────────────────────
# VIN DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>")
def vehicle_detail(vin):
    conn = get_db()
    vehicle = conn.execute("SELECT * FROM vehicles WHERE vin=?", (vin,)).fetchone()
    if not vehicle:
        conn.close()
        return "VIN not found", 404

    observations = conn.execute("""
        SELECT * FROM listing_observations
        WHERE vin=? ORDER BY observed_at DESC
    """, (vin,)).fetchall()

    # Group observations by source_listing_id so UI can show timelines
    ad_groups = {}
    ungrouped = []
    for o in observations:
        slid = o["source_listing_id"]
        if slid:
            key = f"{o['source']}::{slid}"
            ad_groups.setdefault(key, []).append(o)
        else:
            ungrouped.append(o)

    conditions = conn.execute(
        "SELECT * FROM condition_reports WHERE vin=? ORDER BY report_date DESC", (vin,)).fetchall()

    tags = conn.execute("SELECT tag, source_method, created_at FROM tags WHERE vin=?", (vin,)).fetchall()

    corrections = conn.execute(
        "SELECT * FROM vin_correction_log WHERE old_vin=? OR new_vin=? ORDER BY created_at DESC",
        (vin, vin)).fetchall()

    # Price timeline for chart (all observations with price)
    price_timeline = conn.execute("""
        SELECT observed_at, price_pln, source, source_method
        FROM listing_observations
        WHERE vin=? AND price_pln IS NOT NULL
        ORDER BY observed_at ASC
    """, (vin,)).fetchall()

    # Fetch original data for rich view
    orig = conn.execute("""
        SELECT photos, equipment, raw_description,
               ai_summary, ai_equipment, ai_reasoning, ai_suggested_market, ai_interior_color, ai_conflict
        FROM pending_listings
        WHERE vin=?
        ORDER BY scraped_at DESC LIMIT 1
    """, (vin,)).fetchone()
    
    photos = []
    equipment = []
    raw_desc = ""
    ai_data = {
        "summary": vehicle["ai_summary"] if "ai_summary" in vehicle.keys() else None,
        "equipment": [],
        "reasoning": None,
        "market": None,
        "interior": vehicle["color_int"] if "color_int" in vehicle.keys() else None,
        "has_conflict": False,
    }
    if orig:
        photos = json.loads(orig["photos"]) if orig["photos"] else []
        equipment = json.loads(orig["equipment"]) if orig["equipment"] else []
        raw_desc = orig["raw_description"]
        if orig["ai_summary"]:
            ai_data["summary"] = orig["ai_summary"]
        if orig["ai_equipment"]:
            try:
                ai_data["equipment"] = json.loads(orig["ai_equipment"]) if isinstance(orig["ai_equipment"], str) else orig["ai_equipment"]
            except Exception:
                ai_data["equipment"] = []
        ai_data["reasoning"] = orig["ai_reasoning"]
        ai_data["market"] = orig["ai_suggested_market"]
        if orig["ai_interior_color"]:
            ai_data["interior"] = orig["ai_interior_color"]
        ai_data["has_conflict"] = bool(orig["ai_conflict"])

    # CEPiK report
    cepik_data = None
    try:
        cepik_row = conn.execute("SELECT * FROM cepik_reports WHERE vin=?", (vin,)).fetchone()
        if cepik_row:
            c_dict = dict(cepik_row)
            c_dict["odometer_history"] = json.loads(c_dict["odometer_history_json"]) if c_dict.get("odometer_history_json") else []
            c_dict["events"] = json.loads(c_dict["events_json"]) if c_dict.get("events_json") else []
            cepik_data = c_dict
    except Exception:
        cepik_data = None

    # Check if vehicle is eligible to fetch CEPiK
    first_reg = conn.execute("""
        SELECT first_registration_date FROM pending_listings 
        WHERE vin=? AND first_registration_date IS NOT NULL AND first_registration_date != ''
        ORDER BY id DESC LIMIT 1
    """, (vin,)).fetchone()
    can_fetch_cepik = bool(vehicle["registration_plate"] and first_reg and first_reg["first_registration_date"])

    conn.close()
    return render_template("vehicle.html",
        vehicle=vehicle,
        ad_groups=ad_groups,
        ungrouped=ungrouped,
        observations=observations,
        conditions=conditions,
        tags=tags,
        corrections=corrections,
        price_timeline=json.dumps([dict(r) for r in price_timeline]),
        photos=photos,
        equipment=equipment,
        raw_desc=raw_desc,
        ai_data=ai_data,
        cepik_data=cepik_data,
        can_fetch_cepik=can_fetch_cepik,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADD VEHICLE
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/add", methods=["GET", "POST"])
def add_vehicle():
    if request.method == "POST":
        data = request.form
        vin  = data["vin"].strip().upper()
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO vehicles
                  (vin,make,model,variant,year,body_type,engine_cc,engine_cyl,
                   power_hp,drivetrain,transmission,color_ext,color_int,
                   vin_status,notes,source_method)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                vin, data["make"], data["model"],
                data.get("variant") or None,
                safe_int(data.get("year")),
                data.get("body_type") or None,
                safe_int(data.get("engine_cc")),
                safe_int(data.get("engine_cyl")),
                safe_int(data.get("power_hp")),
                data.get("drivetrain")    or None,
                data.get("transmission")  or None,
                data.get("color_ext")     or None,
                data.get("color_int")     or None,
                data.get("vin_status", "unverified"),
                data.get("notes")         or None,
                "manual",
            ))

            # Optional first observation
            if data.get("price_pln") or data.get("mileage_km"):
                conn.execute("""
                    INSERT INTO listing_observations
                      (vin,source,source_url,price_pln,mileage_km,
                       location_city,seller_type,first_seen_at,observed_at,source_method,notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    vin,
                    data.get("source", "manual"),
                    data.get("source_url") or None,
                    safe_float(data.get("price_pln")),
                    safe_int(data.get("mileage_km")),
                    data.get("location_city") or None,
                    data.get("seller_type", "private"),
                    NOW(), NOW(),
                    "manual",
                    data.get("listing_notes") or None,
                ))

            for tag in [t.strip() for t in data.get("tags","").split(",") if t.strip()]:
                conn.execute(
                    "INSERT OR IGNORE INTO tags(vin,tag,source_method) VALUES(?,?,'manual')",
                    (vin, tag))

            conn.commit()
        except Exception as e:
            conn.close()
            return render_template("add_vehicle.html", error=str(e), form=data)
        conn.close()
        return redirect(url_for("vehicles.vehicle_detail", vin=vin))

    return render_template("add_vehicle.html", error=None, form={})


# ─────────────────────────────────────────────────────────────────────────────
# ADD OBSERVATION (manual, from vehicle detail page)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>/add_observation", methods=["POST"])
def add_observation(vin):
    data = request.form
    conn = get_db()
    conn.execute("""
        INSERT INTO listing_observations
          (vin,source,source_listing_id,source_url,price_pln,price_eur,
           mileage_km,location_city,location_region,seller_type,seller_name,
           first_seen_at,observed_at,last_seen_at,removed_at,
           source_method,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        vin,
        data.get("source","manual"),
        data.get("source_listing_id") or None,
        data.get("source_url") or None,
        safe_float(data.get("price_pln")),
        safe_float(data.get("price_eur")),
        safe_int(data.get("mileage_km")),
        data.get("location_city")  or None,
        data.get("location_region") or (CITY_TO_REGION.get(data.get("location_city")) if data.get("location_city") else None),
        data.get("seller_type","private"),
        data.get("seller_name")    or None,
        data.get("first_seen_at")  or NOW(),
        data.get("observed_at")    or NOW(),
        data.get("last_seen_at")   or None,
        data.get("removed_at")     or None,
        "manual",
        data.get("notes") or None,
    ))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# ADD CONDITION REPORT
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>/add_condition", methods=["POST"])
def add_condition(vin):
    data = request.form
    af = data.get("accident_free")
    conn = get_db()
    conn.execute("""
        INSERT INTO condition_reports
          (vin,report_date,mileage_km,accident_free,service_history,
           condition_score,inspection_by,notes,source_method)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        vin,
        data.get("report_date", datetime.today().strftime("%Y-%m-%d")),
        safe_int(data.get("mileage_km")),
        1 if af=="yes" else (0 if af=="no" else None),
        data.get("service_history")  or None,
        safe_int(data.get("condition_score")),
        data.get("inspection_by")    or None,
        data.get("notes")            or None,
        "manual",
    ))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVE PLACEHOLDER VIN (form POST from vehicle detail)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>/resolve", methods=["POST"])
def resolve_vin(vin):
    new_vin = request.form.get("new_vin","").strip().upper()
    reason  = request.form.get("reason","placeholder resolved")
    if not new_vin:
        return redirect(url_for("vehicles.vehicle_detail", vin=vin))
    try:
        resolve_placeholder(vin, new_vin, reason=reason,
                             corrected_by="manual", source_method="manual")
    except Exception as e:
        return f"VIN resolution failed: {e}", 400
    return redirect(url_for("vehicles.vehicle_detail", vin=new_vin))

@bp.route("/vehicle/<path:vin>/update_status", methods=["POST"])
def update_status(vin):
    new_status = request.form.get("vin_status", "unverified")
    conn = get_db()
    conn.execute("UPDATE vehicles SET vin_status=? WHERE vin=?", (new_status, vin))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# TAGS — add / delete from vehicle detail page
# ─────────────────────────────────────────────────────────────────────────────


@bp.route("/vehicle/<path:vin>/update_details", methods=["POST"])
def update_vehicle_details(vin):
    conn = get_db()
    try:
        reg_plate = request.form.get("registration_plate")
        reg_plate = reg_plate.strip().upper() if reg_plate else None
        conn.execute('''
            UPDATE vehicles
            SET year = ?, body_type = ?, engine_cc = ?, engine_cyl = ?,
                power_hp = ?, drivetrain = ?, transmission = ?, color_ext = ?,
                color_int = ?, registration_plate = ?, first_registration_date = ?,
                vin_status = CASE 
                    WHEN vin LIKE 'UNVERIFIED%' THEN 'placeholder' 
                    WHEN ? IS NOT NULL AND ? != '' THEN 'verified' 
                    ELSE vin_status 
                END
            WHERE vin = ?
        ''', (
            request.form.get("year", type=int) or None,
            request.form.get("body_type") or None,
            request.form.get("engine_cc", type=int) or None,
            request.form.get("engine_cyl", type=int) or None,
            request.form.get("power_hp", type=int) or None,
            request.form.get("drivetrain") or None,
            request.form.get("transmission") or None,
            request.form.get("color_ext") or None,
            request.form.get("color_int") or None,
            reg_plate,
            request.form.get("first_registration_date") or None,
            reg_plate,
            reg_plate,
            vin
        ))
        conn.commit()
    except Exception as e:
        print("Error updating vehicle:", e)
    finally:
        conn.close()
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))

@bp.route("/vehicle/<path:vin>/add_tag", methods=["POST"])
def add_tag(vin):
    tag = request.form.get("tag", "").strip()
    if tag:
        conn = get_db()
        conn.execute(
            "INSERT OR IGNORE INTO tags(vin,tag,source_method) VALUES(?,?,'manual')",
            (vin, tag)
        )
        conn.commit()
        conn.close()
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


@bp.route("/vehicle/<path:vin>/delete_tag", methods=["POST"])
def delete_tag(vin):
    tag = request.form.get("tag", "").strip()
    if tag:
        conn = get_db()
        conn.execute("DELETE FROM tags WHERE vin=? AND tag=?", (vin, tag))
        conn.commit()
        conn.close()
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE VEHICLE — requires typing the VIN to confirm
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>/delete", methods=["POST"])
def delete_vehicle(vin):
    confirm = request.form.get("confirm_vin", "").strip().upper()
    if confirm != vin.upper():
        return redirect(url_for("vehicles.vehicle_detail", vin=vin) + "?delete_error=1")
    conn = get_db()
    conn.execute("DELETE FROM listing_observations WHERE vin=?", (vin,))
    conn.execute("DELETE FROM condition_reports WHERE vin=?", (vin,))
    conn.execute("DELETE FROM tags WHERE vin=?", (vin,))
    conn.execute("DELETE FROM vin_correction_log WHERE old_vin=? OR new_vin=?", (vin, vin))
    conn.execute("DELETE FROM vehicles WHERE vin=?", (vin,))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicles.vehicles_list"))
