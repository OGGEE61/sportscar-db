import os

from flask import Blueprint, redirect, render_template, request, url_for
from db import get_db
from webapp import invalidate_notifications
from webapp.helpers import script_json
from webapp.model_catalog import DEFAULT_MODEL_ID, STANDARD_MODELS, get_model
from webapp.regions import CITY_TO_REGION, REGION_NAMES, resolve_region

bp = Blueprint("dashboard", __name__)

LOGS_PER_PAGE = 100


_S3_CLIENT = None


def _s3():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        import boto3
        _S3_CLIENT = boto3.client(
            "s3",
            endpoint_url=os.environ.get("R2_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
    return _S3_CLIENT


@bp.route("/media/<path:filename>")
def serve_media(filename):
    """Serve photo from R2 public URL / presigned URL, or local disk."""
    public = os.environ.get("R2_PUBLIC_URL")  # e.g. https://pub-xxxx.r2.dev
    if public:
        resp = redirect(f"{public.rstrip('/')}/{filename}")
    elif os.environ.get("R2_ENDPOINT_URL") and os.environ.get("R2_BUCKET_NAME"):
        url = _s3().generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": os.environ["R2_BUCKET_NAME"], "Key": filename},
            ExpiresIn=3600,
        )
        resp = redirect(url)
    else:
        resp = redirect(url_for("static", filename=filename))
    # Browser re-uses the redirect for 50 min (presigned URL lives 60 min)
    resp.headers["Cache-Control"] = "private, max-age=3000"
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/logs")
def logs():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    source = request.args.get("source", "")
    source = source if source in ("olx", "otomoto") else ""
    conn = get_db()
    # Older rows have no source: fall back to the run's list URL
    url_src = ("CASE WHEN list_url LIKE '%olx.pl%' THEN 'olx' "
               "WHEN list_url LIKE '%otomoto.pl%' THEN 'otomoto' END")
    try:
        conn.execute("SELECT source FROM scraper_logs LIMIT 1").fetchall()
        src_expr = f"COALESCE(source, {url_src})"
    except Exception:  # database not migrated yet (python db.py)
        src_expr = url_src
    where, params = (f" WHERE {src_expr} = ?", [source]) if source else ("", [])
    total = conn.execute(f"SELECT COUNT(*) FROM scraper_logs{where}", params).fetchone()[0]
    pages = max((total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE, 1)
    page = min(page, pages)
    logs_data = conn.execute(
        f"SELECT *, {src_expr} AS src FROM scraper_logs{where} ORDER BY run_date DESC LIMIT ? OFFSET ?",
        (*params, LOGS_PER_PAGE, (page - 1) * LOGS_PER_PAGE),
    ).fetchall()
    # Mark as read
    conn.execute("UPDATE scraper_logs SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    conn.close()
    invalidate_notifications()  # badge should drop to 0 right away
    return render_template("logs.html", logs=logs_data, page=page, pages=pages, source=source)

@bp.route("/")
def dashboard():
    conn = get_db()

    s = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM vehicles)                                                          AS total_vins,
            (SELECT COUNT(*) FROM vehicles WHERE vin_status='placeholder')                          AS placeholder_vins,
            (SELECT COUNT(*) FROM listing_observations)                                              AS total_obs,
            (SELECT COUNT(DISTINCT source_listing_id) FROM listing_observations WHERE removed_at IS NULL AND source_listing_id IS NOT NULL) AS active_obs,
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

    # Filters from interactive charts / query params
    filter_region = request.args.get("region", "").strip()
    filter_make = request.args.get("make", "").strip()
    filter_price = request.args.get("price", "").strip()
    filter_ai_plates = request.args.get("ai_plates", "").strip()

    recent_sql = """
        SELECT v.vin, v.make, v.model, v.variant, v.year, v.power_hp, v.vin_status, v.photo, v.registration_plate,
               o.price_pln, o.mileage_km, o.location_city, o.location_region, o.source, o.source_method, o.observed_at, o.source_url,
               (SELECT 1 FROM tags t WHERE t.vin = v.vin AND t.tag IN ('photo extracted', 'AI extracted plate')) AS has_ai_plate
        FROM listing_observations o
        JOIN vehicles v ON o.vin = v.vin
    """
    wheres = []
    params = []
    active_filter = None

    if filter_ai_plates == "1":
        wheres.append("(SELECT 1 FROM tags t WHERE t.vin = v.vin AND t.tag IN ('photo extracted', 'AI extracted plate')) IS NOT NULL")
        active_filter = {"type": "ai_plates", "val": "1", "label": "Tablice odczytane ze zdjęcia"}
    elif filter_make:
        wheres.append("v.make = ?")
        params.append(filter_make)
        active_filter = {"type": "make", "val": filter_make, "label": f"Make: {filter_make}"}
    elif filter_price:
        norm_p = filter_price.replace("–", "-")
        if norm_p == "<100k":
            wheres.append("o.price_pln < 100000")
        elif "100" in norm_p and "200" in norm_p:
            wheres.append("o.price_pln >= 100000 AND o.price_pln < 200000")
        elif "200" in norm_p and "350" in norm_p:
            wheres.append("o.price_pln >= 200000 AND o.price_pln < 350000")
        elif "350" in norm_p and "500" in norm_p:
            wheres.append("o.price_pln >= 350000 AND o.price_pln < 500000")
        elif "500" in norm_p and "750" in norm_p:
            wheres.append("o.price_pln >= 500000 AND o.price_pln < 750000")
        elif ">750k" in norm_p or "750" in norm_p:
            wheres.append("o.price_pln >= 750000")
        active_filter = {"type": "price", "val": filter_price, "label": f"Price: {filter_price}"}
    elif filter_region:
        cities_in_region = [c for c, r in CITY_TO_REGION.items() if r == filter_region]
        if cities_in_region:
            placeholders = ",".join("?" for _ in cities_in_region)
            wheres.append(f"(o.location_region = ? OR o.location_city IN ({placeholders}))")
            params.append(filter_region)
            params.extend(cities_in_region)
        else:
            wheres.append("o.location_region = ?")
            params.append(filter_region)
        reg_name = REGION_NAMES.get(filter_region, filter_region)
        active_filter = {"type": "region", "val": filter_region, "label": f"Voivodeship: {reg_name} ({filter_region})"}

    if wheres:
        recent_sql += " WHERE " + " AND ".join(wheres)

    limit = 50 if active_filter else 10
    recent_sql += f" ORDER BY o.observed_at DESC LIMIT {limit}"

    recent_rows = conn.execute(recent_sql, params).fetchall()
    recent = []
    for r in recent_rows:
        d = dict(r)
        reg = resolve_region(d.get("location_region"), d.get("location_city")) or ""
        d["region"] = reg
        d["region_name"] = REGION_NAMES.get(reg, "")
        recent.append(d)

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
            END AS rng, COUNT(DISTINCT vin) AS cnt
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

    cities = conn.execute("SELECT location_region, location_city, COUNT(DISTINCT vin) as cnt FROM listing_observations GROUP BY location_region, location_city").fetchall()
    region_counts = {}
    for r in cities:
        reg = resolve_region(r["location_region"], r["location_city"])
        if reg:
            region_counts[reg] = region_counts.get(reg, 0) + r["cnt"]
    
    map_data = [["State", "Observations"]] + [[k, v] for k, v in region_counts.items()]

    scraper_logs = conn.execute(
        "SELECT * FROM scraper_logs ORDER BY run_date DESC LIMIT 5"
    ).fetchall()

    try:
        sess = conn.execute(
            "SELECT session_status, run_date FROM scraper_logs "
            "WHERE session_status IS NOT NULL AND session_status != '' ORDER BY run_date DESC, id DESC LIMIT 1"
        ).fetchone()
    except Exception:  # column not migrated yet
        sess = None
    otomoto_session = dict(sess) if sess and sess["session_status"] != "ok" else None

    conn.close()
    return render_template("dashboard.html",
        otomoto_session=otomoto_session,
        stats=stats, recent=recent,
        makes_dist=script_json([dict(r) for r in makes_dist]),
        price_ranges=script_json([dict(r) for r in price_ranges]),
        weekly=script_json([dict(r) for r in weekly]),
        map_data=script_json(map_data),
        active_filter=active_filter,
        scraper_logs=[dict(r) for r in scraper_logs]
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODEL ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/models")
def model_analytics():
    conn = get_db()

    selected_id = request.args.get("model", DEFAULT_MODEL_ID)
    current_model = get_model(selected_id) or get_model(DEFAULT_MODEL_ID)

    # Strict query matching this exact generation - NO loose cross-model fallback!
    # Cars with a stored model_id are matched by it; only cars not yet assigned
    # fall back to the catalog rule (so 981 and 718 Caymans stop overlapping).
    base_sql = """
        SELECT v.*, 
               (SELECT 1 FROM tags t WHERE t.vin = v.vin AND t.tag IN ('photo extracted', 'AI extracted plate')) as has_ai_plate,
               o.price_pln, o.mileage_km, o.location_city, o.location_region, o.observed_at, o.source_url, o.title
        FROM vehicles v
        LEFT JOIN (
            SELECT vin, price_pln, mileage_km, location_city, location_region, observed_at, source_url, title,
                   ROW_NUMBER() OVER (PARTITION BY vin ORDER BY observed_at DESC) as rn
            FROM listing_observations
            WHERE price_pln IS NOT NULL AND price_pln > 0
        ) o ON v.vin = o.vin AND o.rn = 1
        WHERE {condition}
    """
    rule = current_model['where']
    try:
        rows = conn.execute(
            base_sql.format(condition=f"(v.model_id = ? OR (v.model_id IS NULL AND ({rule})))"),
            (current_model['id'],)).fetchall()
    except Exception:  # model_id column not migrated yet
        rows = conn.execute(base_sql.format(condition=f"({rule})")).fetchall()
    vehicles = [dict(r) for r in rows]

    # Annotate region codes and names for mapping & filtering
    region_counts = {}
    for v in vehicles:
        reg = resolve_region(v.get("location_region"), v.get("location_city"))
        if reg:
            region_counts[reg] = region_counts.get(reg, 0) + 1
            v["region"] = reg
            v["region_name"] = REGION_NAMES.get(reg, reg)
        else:
            v["region"] = ""
            v["region_name"] = ""

    prices = [v["price_pln"] for v in vehicles if v.get("price_pln")]
    mileages = [v["mileage_km"] for v in vehicles if v.get("mileage_km")]

    import statistics
    stats = {
        "count": len(vehicles),
        "avg_price": round(statistics.mean(prices)) if prices else 0,
        "median_price": round(statistics.median(prices)) if prices else 0,
        "min_price": round(min(prices)) if prices else 0,
        "max_price": round(max(prices)) if prices else 0,
        "avg_mileage": round(statistics.mean(mileages)) if mileages else 0,
        "median_mileage": round(statistics.median(mileages)) if mileages else 0,
    }

    # Price vs Mileage scatter data
    scatter_data = []
    for v in vehicles:
        if v.get("price_pln") and v.get("mileage_km"):
            scatter_data.append({
                "x": v["mileage_km"],
                "y": v["price_pln"],
                "vin": v["vin"],
                "year": v.get("year", ""),
                "title": v.get("title") or (f"{v['make']} {v['model']}"),
                "url": f"/vehicle/{v['vin']}",
            })

    # Price brackets (5 bins)
    hist_labels = []
    hist_counts = []
    if prices and len(prices) >= 2 and max(prices) > min(prices):
        min_p, max_p = min(prices), max(prices)
        step = (max_p - min_p) / 5
        bins = [min_p + step * i for i in range(6)]
        for i in range(5):
            b_start = round(bins[i] / 1000) * 1000
            b_end = round(bins[i+1] / 1000) * 1000
            label = f"{b_start//1000}k–{b_end//1000}k"
            cnt = sum(1 for p in prices if bins[i] <= p < bins[i+1] or (i == 4 and p == max_p))
            hist_labels.append(label)
            hist_counts.append(cnt)
    elif prices:
        hist_labels = [f"{round(prices[0]/1000)}k"]
        hist_counts = [len(prices)]

    # Regional Poland map data for this model
    map_data = [["State", "Listings"]] + [[k, v] for k, v in region_counts.items()]

    # Year breakdown
    year_counts = {}
    for v in vehicles:
        y = v.get("year")
        if y:
            year_counts[y] = year_counts.get(y, 0) + 1
    sorted_years = sorted(year_counts.keys())
    year_data = [{"year": str(y), "cnt": year_counts[y]} for y in sorted_years]

    conn.close()

    return render_template(
        "model_analytics.html",
        models=STANDARD_MODELS,
        selected_model=current_model,
        stats=stats,
        vehicles=vehicles,
        scatter_data=script_json(scatter_data),
        hist_labels=script_json(hist_labels),
        hist_counts=script_json(hist_counts),
        map_data=script_json(map_data),
        year_data=script_json(year_data),
    )
