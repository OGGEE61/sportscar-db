from flask import Flask, render_template, request, jsonify, redirect, url_for
from db import get_db, init_db, make_placeholder_vin, resolve_placeholder
from datetime import datetime
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.jinja_env.filters["fromjson"] = json.loads
NOW = lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    conn = get_db()

    s = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM vehicles)                                                          AS total_vins,
            (SELECT COUNT(*) FROM vehicles WHERE vin_status='placeholder')                          AS placeholder_vins,
            (SELECT COUNT(*) FROM listing_observations)                                              AS total_obs,
            (SELECT COUNT(*) FROM listing_observations WHERE removed_at IS NULL)                     AS active_obs,
            (SELECT COUNT(DISTINCT source_listing_id) FROM listing_observations
             WHERE source_listing_id IS NOT NULL)                                                    AS unique_ads,
            (SELECT AVG(price_pln) FROM listing_observations
             WHERE removed_at IS NULL AND price_pln > 0)                                            AS avg_price
    """).fetchone()
    stats = {
        "total_vins":       s["total_vins"],
        "placeholder_vins": s["placeholder_vins"],
        "total_obs":        s["total_obs"],
        "active_obs":       s["active_obs"],
        "unique_ads":       s["unique_ads"],
        "avg_price":        round(s["avg_price"]) if s["avg_price"] else 0,
    }

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
    conn  = get_db()
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
    conn = get_db()
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
        return f"VIN resolution failed: {e}", 400
    return redirect(url_for("vehicle_detail", vin=new_vin))


# ─────────────────────────────────────────────────────────────────────────────
# VIN CORRECTION LOG (global view)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/corrections")
def corrections():
    conn = get_db()
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

    conn = get_db()
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

@app.route("/api/vehicles")
def api_vehicles():
    conn = get_db()
    rows = conn.execute("SELECT * FROM vehicles ORDER BY updated_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER INGEST  (scrapers POST here → pending_listing for manual review)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/ingest_pending", methods=["POST"])
def api_ingest_pending():
    p = request.get_json(force=True)
    conn = get_db()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO pending_listings
              (source, source_listing_id, source_url,
               raw_title, raw_description, photos,
               make, model, variant, year, body_type,
               engine_cc, power_hp, fuel_type,
               drivetrain, transmission, color_ext, doors,
               price_pln, price_eur, mileage_km,
               location_city, location_region,
               seller_type, seller_name,
               vin, vin_confidence, is_listing_active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            p.get("source", "olx"),
            p.get("source_listing_id"),
            p.get("source_url"),
            p.get("raw_title"),
            p.get("raw_description"),
            json.dumps(p.get("photos", [])),
            p.get("make"),
            p.get("model"),
            p.get("variant"),
            p.get("year"),
            p.get("body_type"),
            p.get("engine_cc"),
            p.get("power_hp"),
            p.get("fuel_type"),
            p.get("drivetrain"),
            p.get("transmission"),
            p.get("color_ext"),
            p.get("doors"),
            p.get("price_pln"),
            p.get("price_eur"),
            p.get("mileage_km"),
            p.get("location_city"),
            p.get("location_region"),
            p.get("seller_type"),
            p.get("seller_name"),
            p.get("vin"),
            p.get("vin_confidence", "none"),
            1,  # scraped now = listing is active
        ))
        conn.commit()
        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return jsonify({"status": "ok", "id": lid})
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# REVIEW QUEUE
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/review")
def review_queue():
    status_filter = request.args.get("status", "pending")
    conn = get_db()
    listings = conn.execute("""
        SELECT * FROM pending_listings
        WHERE status = ?
        ORDER BY scraped_at DESC
    """, (status_filter,)).fetchall()
    counts = {r["status"]: r["cnt"] for r in conn.execute("""
        SELECT status, COUNT(*) AS cnt FROM pending_listings GROUP BY status
    """).fetchall()}
    conn.close()
    return render_template("review.html",
        listings=listings, counts=counts, status_filter=status_filter)


@app.route("/review/<int:pid>")
def review_detail(pid):
    conn = get_db()
    listing = conn.execute(
        "SELECT * FROM pending_listings WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not listing:
        return "Not found", 404
    photos = json.loads(listing["photos"]) if listing["photos"] else []
    return render_template("review_detail.html", listing=listing, photos=photos)


@app.route("/review/<int:pid>/approve", methods=["POST"])
def review_approve(pid):
    data = request.form
    conn = get_db()
    listing = conn.execute(
        "SELECT * FROM pending_listings WHERE id=?", (pid,)).fetchone()
    if not listing:
        conn.close()
        return "Not found", 404

    vin = data.get("vin", "").strip().upper()
    if not vin or len(vin) != 17:
        vin = make_placeholder_vin("olx", listing["source_listing_id"] or str(pid))

    try:
        conn.execute("""
            INSERT INTO vehicles
              (vin, make, model, variant, year, body_type,
               engine_cc, power_hp, drivetrain, transmission,
               color_ext, vin_status, source_method)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(vin) DO UPDATE SET
              make        = COALESCE(excluded.make, make),
              model       = COALESCE(excluded.model, model),
              power_hp    = COALESCE(excluded.power_hp, power_hp),
              updated_at  = datetime('now')
        """, (
            vin,
            data.get("make")         or listing["make"]  or "Unknown",
            data.get("model")        or listing["model"] or "Unknown",
            data.get("variant")      or listing["variant"],
            int(data["year"])        if data.get("year")       else (listing["year"] or 0),
            data.get("body_type")    or listing["body_type"],
            int(data["engine_cc"])   if data.get("engine_cc")  else listing["engine_cc"],
            int(data["power_hp"])    if data.get("power_hp")   else listing["power_hp"],
            data.get("drivetrain")   or listing["drivetrain"],
            data.get("transmission") or listing["transmission"],
            data.get("color_ext")    or listing["color_ext"],
            "placeholder" if vin.startswith("UNVERIFIED") else "unverified",
            f"scraper-{listing['source']}",
        ))

        source_method = f"scraper-{listing['source']}"
        conn.execute("""
            INSERT INTO listing_observations
              (vin, source, source_listing_id, source_url, title,
               price_pln, mileage_km, location_city,
               seller_type, seller_name,
               first_seen_at, observed_at, source_method, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vin, listing["source"],
            listing["source_listing_id"],
            listing["source_url"],
            listing["raw_title"],
            float(data["price_pln"])  if data.get("price_pln")  else listing["price_pln"],
            int(data["mileage_km"])   if data.get("mileage_km") else listing["mileage_km"],
            data.get("location_city") or listing["location_city"],
            data.get("seller_type")   or listing["seller_type"] or "private",
            data.get("seller_name")   or listing["seller_name"],
            listing["scraped_at"], listing["scraped_at"],
            source_method,
            data.get("notes"),
        ))

        conn.execute("""
            UPDATE pending_listings
            SET status='approved', reviewed_at=datetime('now'), review_notes=?
            WHERE id=?
        """, (data.get("notes"), pid))
        conn.commit()
    except Exception as e:
        conn.close()
        return f"Error approving listing: {e}", 500

    conn.close()
    return redirect(url_for("vehicle_detail", vin=vin))


@app.route("/review/reject_all_pending")
def review_reject_all_pending():
    conn = get_conn()
    conn.execute(
        "UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') WHERE status='pending'"
    )
    conn.commit()
    conn.close()
    return redirect(url_for("review_queue"))


@app.route("/review/bulk_reject", methods=["POST"])
def review_bulk_reject():
    ids = request.form.getlist("ids")
    if ids:
        conn = get_conn()
        conn.execute(
            f"UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') "
            f"WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        conn.commit()
        conn.close()
    return redirect(url_for("review_queue"))


@app.route("/review/<int:pid>/reject", methods=["POST"])
def review_reject(pid):
    reason = request.form.get("reason", "")
    conn = get_db()
    conn.execute("""
        UPDATE pending_listings
        SET status='rejected', reviewed_at=datetime('now'), review_notes=?
        WHERE id=?
    """, (reason, pid))
    conn.commit()
    conn.close()
    return redirect(url_for("review_queue"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5555)
