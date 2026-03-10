from flask import Flask, render_template, request, jsonify, redirect, url_for
from db import get_conn, init_db, make_placeholder_vin, resolve_placeholder
from datetime import datetime
import json

app = Flask(__name__)
NOW = lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    conn = get_conn()

    stats = {
        "total_vins":        conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
        "placeholder_vins":  conn.execute("SELECT COUNT(*) FROM vehicles WHERE vin_status='placeholder'").fetchone()[0],
        "total_obs":         conn.execute("SELECT COUNT(*) FROM listing_observations").fetchone()[0],
        "active_obs":        conn.execute("SELECT COUNT(*) FROM listing_observations WHERE removed_at IS NULL").fetchone()[0],
        "unique_ads":        conn.execute("SELECT COUNT(DISTINCT source_listing_id) FROM listing_observations WHERE source_listing_id IS NOT NULL").fetchone()[0],
    }
    avg = conn.execute("SELECT AVG(price_pln) FROM listing_observations WHERE removed_at IS NULL AND price_pln > 0").fetchone()[0]
    stats["avg_price"] = round(avg) if avg else 0

    recent = conn.execute("""
        SELECT v.vin, v.make, v.model, v.variant, v.year, v.power_hp, v.vin_status,
               o.price_pln, o.mileage_km, o.source, o.source_method, o.observed_at
        FROM listing_observations o
        JOIN vehicles v ON o.vin = v.vin
        ORDER BY o.observed_at DESC LIMIT 10
    """).fetchall()

    makes_dist = conn.execute("""
        SELECT make, COUNT(*) AS cnt FROM vehicles
        WHERE vin_status != 'placeholder'
        GROUP BY make ORDER BY cnt DESC LIMIT 12
    """).fetchall()

    price_ranges = conn.execute("""
        SELECT
            CASE
                WHEN price_pln <  100000 THEN '<100k'
                WHEN price_pln <  200000 THEN '100–200k'
                WHEN price_pln <  350000 THEN '200–350k'
                WHEN price_pln <  500000 THEN '350–500k'
                WHEN price_pln <  750000 THEN '500–750k'
                ELSE '>750k'
            END AS rng, COUNT(*) AS cnt
        FROM listing_observations
        WHERE price_pln > 0 AND removed_at IS NULL
        GROUP BY rng ORDER BY MIN(price_pln)
    """).fetchall()

    # Observations per week for the last 12 weeks
    weekly = conn.execute("""
        SELECT strftime('%Y-W%W', observed_at) AS week, COUNT(*) AS cnt
        FROM listing_observations
        WHERE observed_at >= datetime('now', '-84 days')
        GROUP BY week ORDER BY week
    """).fetchall()

    # Source breakdown
    sources = conn.execute("""
        SELECT source_method, COUNT(*) AS cnt
        FROM listing_observations GROUP BY source_method
    """).fetchall()

    conn.close()
    return render_template("dashboard.html",
        stats=stats, recent=recent,
        makes_dist=json.dumps([dict(r) for r in makes_dist]),
        price_ranges=json.dumps([dict(r) for r in price_ranges]),
        weekly=json.dumps([dict(r) for r in weekly]),
        sources=json.dumps([dict(r) for r in sources]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# VEHICLES LIST
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicles")
def vehicles_list():
    conn  = get_conn()
    q     = request.args.get("q", "").strip()
    make  = request.args.get("make", "")
    status = request.args.get("status", "")
    sort  = request.args.get("sort", "updated_at")

    base = """
        SELECT v.*,
               COUNT(DISTINCT o.id)                  AS obs_count,
               COUNT(DISTINCT o.source_listing_id)   AS ad_count,
               MIN(o.price_pln)                      AS min_price,
               MAX(o.price_pln)                      AS max_price,
               MAX(o.observed_at)                    AS last_observed,
               GROUP_CONCAT(DISTINCT t.tag)          AS tags
        FROM vehicles v
        LEFT JOIN listing_observations o ON v.vin = o.vin
        LEFT JOIN tags t ON v.vin = t.vin
    """
    wheres, params = [], []
    if q:
        wheres.append("(v.make LIKE ? OR v.model LIKE ? OR v.vin LIKE ? OR v.variant LIKE ?)")
        params += [f"%{q}%"] * 4
    if make:
        wheres.append("v.make = ?"); params.append(make)
    if status:
        wheres.append("v.vin_status = ?"); params.append(status)

    if wheres:
        base += " WHERE " + " AND ".join(wheres)
    base += " GROUP BY v.vin"

    sort_map = {
        "updated_at": "v.updated_at DESC",
        "year_desc":  "v.year DESC",
        "year_asc":   "v.year ASC",
        "power":      "v.power_hp DESC",
        "obs":        "obs_count DESC",
        "price":      "min_price ASC NULLS LAST",
    }
    base += " ORDER BY " + sort_map.get(sort, "v.updated_at DESC")

    vehicles = conn.execute(base, params).fetchall()
    makes    = conn.execute("SELECT DISTINCT make FROM vehicles ORDER BY make").fetchall()
    conn.close()
    return render_template("vehicles.html",
        vehicles=vehicles, makes=[m["make"] for m in makes],
        q=q, selected_make=make, status=status, sort=sort)


# ─────────────────────────────────────────────────────────────────────────────
# VIN DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicle/<path:vin>")
def vehicle_detail(vin):
    conn = get_conn()
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
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADD VEHICLE
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/add", methods=["GET", "POST"])
def add_vehicle():
    if request.method == "POST":
        data = request.form
        vin  = data["vin"].strip().upper()
        conn = get_conn()
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
                int(data["year"]),
                data.get("body_type") or None,
                int(data["engine_cc"])  if data.get("engine_cc")  else None,
                int(data["engine_cyl"]) if data.get("engine_cyl") else None,
                int(data["power_hp"])   if data.get("power_hp")   else None,
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
                    float(data["price_pln"])  if data.get("price_pln")  else None,
                    int(data["mileage_km"])   if data.get("mileage_km") else None,
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
        return redirect(url_for("vehicle_detail", vin=vin))

    return render_template("add_vehicle.html", error=None, form={})


# ─────────────────────────────────────────────────────────────────────────────
# ADD OBSERVATION (manual, from vehicle detail page)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicle/<path:vin>/add_observation", methods=["POST"])
def add_observation(vin):
    data = request.form
    conn = get_conn()
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
        float(data["price_pln"])   if data.get("price_pln")   else None,
        float(data["price_eur"])   if data.get("price_eur")   else None,
        int(data["mileage_km"])    if data.get("mileage_km")  else None,
        data.get("location_city")  or None,
        data.get("location_region")or None,
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
    return redirect(url_for("vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# ADD CONDITION REPORT
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicle/<path:vin>/add_condition", methods=["POST"])
def add_condition(vin):
    data = request.form
    af = data.get("accident_free")
    conn = get_conn()
    conn.execute("""
        INSERT INTO condition_reports
          (vin,report_date,mileage_km,accident_free,service_history,
           condition_score,inspection_by,notes,source_method)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        vin,
        data.get("report_date", datetime.today().strftime("%Y-%m-%d")),
        int(data["mileage_km"])      if data.get("mileage_km")      else None,
        1 if af=="yes" else (0 if af=="no" else None),
        data.get("service_history")  or None,
        int(data["condition_score"]) if data.get("condition_score") else None,
        data.get("inspection_by")    or None,
        data.get("notes")            or None,
        "manual",
    ))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVE PLACEHOLDER VIN (form POST from vehicle detail)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicle/<path:vin>/resolve", methods=["POST"])
def resolve_vin(vin):
    new_vin = request.form.get("new_vin","").strip().upper()
    reason  = request.form.get("reason","placeholder resolved")
    if not new_vin:
        return redirect(url_for("vehicle_detail", vin=vin))
    try:
        resolve_placeholder(vin, new_vin, reason=reason,
                             corrected_by="manual", source_method="manual")
    except Exception as e:
        # TODO: flash error
        pass
    return redirect(url_for("vehicle_detail", vin=new_vin))


# ─────────────────────────────────────────────────────────────────────────────
# VIN CORRECTION LOG (global view)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/corrections")
def corrections():
    conn = get_conn()
    log = conn.execute(
        "SELECT * FROM vin_correction_log ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("corrections.html", log=log)


# ─────────────────────────────────────────────────────────────────────────────
# REST API  (for future scrapers)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    """
    Scrapers POST here. One payload = one observation row.
    If VIN is missing/invalid, a placeholder is created automatically.
    """
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

    conn = get_conn()
    # Upsert vehicle (placeholder or real)
    is_placeholder = vin.startswith("UNVERIFIED")
    conn.execute("""
        INSERT INTO vehicles(vin,make,model,variant,year,body_type,
            engine_cc,engine_cyl,power_hp,drivetrain,transmission,color_ext,
            vin_status,source_method)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vin) DO UPDATE SET
            make        = COALESCE(excluded.make, make),
            model       = COALESCE(excluded.model, model),
            power_hp    = COALESCE(excluded.power_hp, power_hp),
            updated_at  = datetime('now')
    """, (
        vin,
        p.get("make","Unknown"), p.get("model","Unknown"),
        p.get("variant"), p.get("year", 0),
        p.get("body_type"),
        p.get("engine_cc"), p.get("engine_cyl"), p.get("power_hp"),
        p.get("drivetrain"), p.get("transmission"), p.get("color_ext"),
        "placeholder" if is_placeholder else "unverified",
        f"scraper-{source}" if source in ("otomoto","olx") else "api",
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
        p.get("price_pln"), p.get("price_eur"),
        p.get("mileage_km"),
        p.get("location_city"), p.get("location_region"),
        p.get("seller_type"), p.get("seller_name"),
        p.get("first_seen_at") or NOW(),
        p.get("observed_at")   or NOW(),
        p.get("last_seen_at"),
        p.get("removed_at"),
        f"scraper-{source}" if source in ("otomoto","olx") else "api",
        p.get("notes"),
    ))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "vin": vin, "observation_id": c.lastrowid,
                    "is_placeholder": is_placeholder})


@app.route("/api/stats")
def api_stats():
    conn = get_conn()
    data = {
        "total_vins":       conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
        "placeholder_vins": conn.execute("SELECT COUNT(*) FROM vehicles WHERE vin_status='placeholder'").fetchone()[0],
        "total_observations": conn.execute("SELECT COUNT(*) FROM listing_observations").fetchone()[0],
        "sources":          dict(conn.execute("SELECT source_method, COUNT(*) FROM listing_observations GROUP BY source_method").fetchall()),
        "schema_version":   conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
    }
    conn.close()
    return jsonify(data)

@app.route("/api/vehicles")
def api_vehicles():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM vehicles ORDER BY updated_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5555)
