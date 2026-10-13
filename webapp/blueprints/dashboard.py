import json
import os

from flask import Blueprint, redirect, render_template, request, url_for
from db import get_db
from webapp.regions import CITY_TO_REGION, REGION_NAMES, REGION_NAME_TO_CODE

bp = Blueprint("dashboard", __name__)


@bp.route("/media/<path:filename>")
def serve_media(filename):
    """Serve photo from R2 presigned URL or local disk."""
    endpoint = os.environ.get("R2_ENDPOINT_URL")
    bucket = os.environ.get("R2_BUCKET_NAME")
    if endpoint and bucket:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
            region_name="auto"
        )
        url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket, 'Key': filename},
            ExpiresIn=3600
        )
        return redirect(url)
    return redirect(url_for('static', filename=filename))


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/logs")
def logs():
    conn = get_db()
    logs_data = conn.execute("SELECT * FROM scraper_logs ORDER BY run_date DESC").fetchall()
    # Mark as read
    conn.execute("UPDATE scraper_logs SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    return render_template("logs.html", logs=logs_data)

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
        reg = d.get("location_region")
        if not reg or len(reg) != 5:
            reg = CITY_TO_REGION.get(d.get("location_city"), "")
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
        reg = r["location_region"]
        if not reg or len(reg) != 5:
            city = r["location_city"]
            if city and city in CITY_TO_REGION:
                reg = CITY_TO_REGION[city]
            else:
                reg = None
                
        if reg:
            region_counts[reg] = region_counts.get(reg, 0) + r["cnt"]
    
    map_data = [["State", "Observations"]] + [[k, v] for k, v in region_counts.items()]

    scraper_logs = conn.execute(
        "SELECT * FROM scraper_logs ORDER BY run_date DESC LIMIT 5"
    ).fetchall()

    conn.close()
    return render_template("dashboard.html",
        stats=stats, recent=recent,
        makes_dist=json.dumps([dict(r) for r in makes_dist]),
        price_ranges=json.dumps([dict(r) for r in price_ranges]),
        weekly=json.dumps([dict(r) for r in weekly]),
        map_data=json.dumps(map_data),
        active_filter=active_filter,
        scraper_logs=[dict(r) for r in scraper_logs]
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODEL ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/models")
def model_analytics():
    conn = get_db()

    STANDARD_MODELS = [
        {
            "id": "alpina_bmw",
            "name": "Alpina BMW (B3 / B5 / D3 / D5)",
            "make": "Alpina",
            "model": "Alpina",
            "variant": "B3 / B5 / D3 / D5",
            "years": "2005–",
            "engine": "Biturbo / D-Turbo · 350-600 HP · RWD/AWD",
            "where": "(v.make = 'Alpina' OR v.variant LIKE '%Alpina%' OR v.model LIKE '%Alpina%')"
        },
        {
            "id": "audi_r8_v8",
            "name": "Audi R8 V8 (Type 42)",
            "make": "Audi",
            "model": "R8",
            "variant": "Type 42 V8",
            "years": "2007–2015",
            "engine": "4.2L V8 FSI · 420-430 HP · Quattro",
            "where": "v.make = 'Audi' AND v.model = 'R8' AND (v.variant LIKE '%V8%' OR v.power_hp < 500)"
        },
        {
            "id": "audi_r8_v10",
            "name": "Audi R8 V10 (Type 42 / 4S)",
            "make": "Audi",
            "model": "R8",
            "variant": "Type 42 / 4S V10",
            "years": "2009–2023",
            "engine": "5.2L V10 FSI · 525-620 HP · Quattro",
            "where": "v.make = 'Audi' AND v.model = 'R8' AND (v.variant LIKE '%V10%' OR v.power_hp >= 500)"
        },
        {
            "id": "rs3_8v",
            "name": "Audi RS3 (8V)",
            "make": "Audi",
            "model": "RS3",
            "variant": "8V",
            "years": "2015–2020",
            "engine": "2.5L TFSI · 367-400 HP · Quattro",
            "where": "v.make = 'Audi' AND (v.model = 'RS3' OR v.variant LIKE '%8V%')"
        },
        {
            "id": "rs4_b85",
            "name": "Audi RS4 B8.5 Avant",
            "make": "Audi",
            "model": "RS4",
            "variant": "B8.5 Avant",
            "years": "2013–2015",
            "engine": "4.2L V8 FSI · 450 HP · Quattro",
            "where": "v.make = 'Audi' AND v.model = 'RS4' AND (v.variant LIKE '%B8%' OR (v.year >= 2012 AND v.year <= 2016)) AND (v.variant NOT LIKE '%B9%' AND (v.year <= 2016 OR v.year IS NULL))"
        },
        {
            "id": "rs4_b9",
            "name": "Audi RS4 B9 Avant",
            "make": "Audi",
            "model": "RS4",
            "variant": "B9 Avant",
            "years": "2017–2024",
            "engine": "2.9L V6 Biturbo · 450 HP · Quattro",
            "where": "v.make = 'Audi' AND v.model = 'RS4' AND (v.variant LIKE '%B9%' OR (v.year >= 2017 AND v.year <= 2024)) AND (v.variant NOT LIKE '%B8%' AND (v.year >= 2017 OR v.year IS NULL))"
        },
        {
            "id": "ttrs",
            "name": "Audi TT RS",
            "make": "Audi",
            "model": "TT",
            "variant": "TT RS",
            "years": "2009–2023",
            "engine": "2.5L TFSI · 340-400 HP · Quattro",
            "where": "v.make = 'Audi' AND (v.model = 'TT RS' OR (v.model = 'TT' AND (v.variant LIKE '%RS%' OR v.power_hp >= 340)))"
        },
        {
            "id": "bmw_135i_e82",
            "name": "BMW 135i (E82/E88)",
            "make": "BMW",
            "model": "Seria 1",
            "variant": "135i E82/E88",
            "years": "2007–2013",
            "engine": "3.0L Turbo N54/N55 · 306 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'Seria 1' OR v.model = '135i') AND (v.variant LIKE '%135i%' OR v.notes LIKE '%135i%')"
        },
        {
            "id": "bmw_1m_e82",
            "name": "BMW 1M Coupe (E82)",
            "make": "BMW",
            "model": "Seria 1",
            "variant": "1M E82",
            "years": "2011–2012",
            "engine": "3.0L Twin-Turbo N54 · 340 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'Seria 1' OR v.model = '1M') AND (v.variant LIKE '%1M%' OR v.notes LIKE '%1M%')"
        },
        {
            "id": "m2_f87",
            "name": "BMW M2 (F87)",
            "make": "BMW",
            "model": "M2",
            "variant": "F87",
            "years": "2016–2021",
            "engine": "3.0L N55/S55 · 370-450 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'M2' OR v.variant LIKE '%F87%') AND (v.variant LIKE '%F87%' OR (v.year >= 2015 AND v.year <= 2021))"
        },
        {
            "id": "m2_g87",
            "name": "BMW M2 (G87)",
            "make": "BMW",
            "model": "M2",
            "variant": "G87",
            "years": "2023–",
            "engine": "3.0L Twin-Turbo S58 · 460-480 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'M2' OR v.variant LIKE '%G87%') AND (v.variant LIKE '%G87%' OR v.year >= 2022)"
        },
        {
            "id": "bmw_m3_e46",
            "name": "BMW M3 (E46)",
            "make": "BMW",
            "model": "M3",
            "variant": "E46 M3",
            "years": "2000–2006",
            "engine": "3.2L NA S54 · 343 HP · RWD",
            "where": "v.make = 'BMW' AND v.model = 'M3' AND (v.variant LIKE '%E46%' OR (v.year >= 2000 AND v.year <= 2006))"
        },
        {
            "id": "m3_f80",
            "name": "BMW M3 (F80)",
            "make": "BMW",
            "model": "M3",
            "variant": "F80",
            "years": "2014–2018",
            "engine": "3.0L Twin-Turbo S55 · 431-460 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'M3' OR v.variant LIKE '%F80%') AND (v.variant LIKE '%F80%' OR (v.year >= 2014 AND v.year <= 2019))"
        },
        {
            "id": "m4_f82",
            "name": "BMW M4 (F82)",
            "make": "BMW",
            "model": "M4",
            "variant": "F82",
            "years": "2014–2020",
            "engine": "3.0L Twin-Turbo S55 · 431-500 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'M4' OR v.variant LIKE '%F82%' OR v.variant LIKE '%F83%') AND (v.year >= 2014 AND v.year <= 2020)"
        },
        {
            "id": "bmw_m5_e39",
            "name": "BMW M5 (E39)",
            "make": "BMW",
            "model": "M5",
            "variant": "E39 M5",
            "years": "1998–2003",
            "engine": "4.9L V8 NA S62 · 400 HP · RWD",
            "where": "v.make = 'BMW' AND v.model = 'M5' AND (v.variant LIKE '%E39%' OR (v.year >= 1998 AND v.year <= 2003))"
        },
        {
            "id": "x3_m_f97",
            "name": "BMW X3 M (F97)",
            "make": "BMW",
            "model": "X3 M",
            "variant": "F97",
            "years": "2019–2024",
            "engine": "3.0L Twin-Turbo S58 · 480-510 HP · AWD",
            "where": "v.make = 'BMW' AND (v.model = 'X3 M' OR (v.model = 'X3' AND v.variant LIKE '%F97%')) AND (v.variant NOT LIKE '%M40i%' AND v.model NOT LIKE '%M40i%')"
        },
        {
            "id": "x3_m40i_g01",
            "name": "BMW X3 M40i (G01)",
            "make": "BMW",
            "model": "X3",
            "variant": "M40i G01",
            "years": "2017–2024",
            "engine": "3.0L Turbo B58 · 360 HP · AWD",
            "where": "v.make = 'BMW' AND (v.model = 'X3' OR v.model = 'X3 M40i') AND (v.variant LIKE '%M40i%' OR v.variant LIKE '%G01%') AND (v.model != 'X3 M' AND v.variant NOT LIKE '%F97%')"
        },
        {
            "id": "bmw_z3_m",
            "name": "BMW Z3 M (Coupe / Roadster)",
            "make": "BMW",
            "model": "Z3",
            "variant": "Z3 M",
            "years": "1997–2002",
            "engine": "3.2L NA S50/S54 · 321-325 HP · RWD",
            "where": "v.make = 'BMW' AND v.model = 'Z3' AND (v.variant LIKE '%Z3 M%' OR v.power_hp >= 300)"
        },
        {
            "id": "honda_s2000",
            "name": "Honda S2000",
            "make": "Honda",
            "model": "S2000",
            "variant": "AP1 / AP2",
            "years": "1999–2009",
            "engine": "2.0L VTEC F20C · 240 HP · RWD",
            "where": "v.make = 'Honda' AND v.model = 'S2000'"
        },
        {
            "id": "a45_w176",
            "name": "Mercedes A45 AMG (W176)",
            "make": "Mercedes-Benz",
            "model": "Klasa A",
            "variant": "W176 A45 AMG",
            "years": "2013–2018",
            "engine": "2.0L Turbo M133 · 360-381 HP · 4MATIC",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa A' OR v.model LIKE '%A 45%' OR v.model LIKE '%A45%') AND (v.variant LIKE '%W176%' OR v.variant LIKE '%A45%' OR v.power_hp >= 360)"
        },
        {
            "id": "c63_w204",
            "name": "Mercedes C63 AMG (W204)",
            "make": "Mercedes-Benz",
            "model": "Klasa C",
            "variant": "W204 C63 AMG",
            "years": "2008–2015",
            "engine": "6.2L V8 M156 · 457-507 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%W204%' OR v.variant LIKE '%C63%' OR v.variant LIKE '%C 63%' OR (v.model = 'Klasa C' AND (v.power_hp >= 450 OR v.engine_cc > 6000)))"
        },
        {
            "id": "cl55_c215",
            "name": "Mercedes CL55 AMG (C215)",
            "make": "Mercedes-Benz",
            "model": "CL",
            "variant": "CL55 AMG C215",
            "years": "2002–2006",
            "engine": "5.4L V8 Kompressor M113K · 500 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'CL' OR v.variant LIKE '%CL55%' OR v.variant LIKE '%C215%') AND (v.variant LIKE '%CL55%' OR v.power_hp >= 490)"
        },
        {
            "id": "clk63_w209",
            "name": "Mercedes CLK63 AMG (W209)",
            "make": "Mercedes-Benz",
            "model": "Klasa CLK",
            "variant": "W209 CLK 63 AMG",
            "years": "2006–2009",
            "engine": "6.2L V8 M156 · 481 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa CLK' OR v.variant LIKE '%CLK 63%' OR v.variant LIKE '%CLK63%')"
        },
        {
            "id": "cls55_c219",
            "name": "Mercedes CLS55 AMG (C219)",
            "make": "Mercedes-Benz",
            "model": "CLS",
            "variant": "C219 CLS 55 AMG",
            "years": "2004–2006",
            "engine": "5.4L V8 Kompressor M113K · 476 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%C219%' OR v.variant LIKE '%CLS 55%' OR v.variant LIKE '%CLS55%' OR (v.model = 'CLS' AND (v.power_hp >= 460 OR v.engine_cc = 5439)))"
        },
        {
            "id": "e55_w211",
            "name": "Mercedes E55 AMG (W211)",
            "make": "Mercedes-Benz",
            "model": "Klasa E",
            "variant": "W211 E55 AMG",
            "years": "2003–2006",
            "engine": "5.4L V8 Kompressor M113K · 476 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%W211%' OR v.variant LIKE '%E55%' OR v.variant LIKE '%E 55%' OR (v.model = 'Klasa E' AND (v.power_hp >= 460 OR v.engine_cc = 5439)))"
        },
        {
            "id": "g55_w463",
            "name": "Mercedes G55 AMG (W463)",
            "make": "Mercedes-Benz",
            "model": "Klasa G",
            "variant": "G55 AMG W463",
            "years": "2004–2012",
            "engine": "5.4L V8 Kompressor M113K · 476-507 HP · 4WD",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa G' OR v.variant LIKE '%G55%' OR v.variant LIKE '%W463%') AND (v.variant LIKE '%G55%' OR v.power_hp >= 470)"
        },
        {
            "id": "gla45_x156",
            "name": "Mercedes GLA45 AMG (X156)",
            "make": "Mercedes-Benz",
            "model": "GLA",
            "variant": "GLA45 AMG X156",
            "years": "2014–2019",
            "engine": "2.0L Turbo M133 · 360-381 HP · 4MATIC",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'GLA' OR v.variant LIKE '%GLA45%' OR v.variant LIKE '%X156%') AND (v.variant LIKE '%GLA45%' OR v.power_hp >= 360)"
        },
        {
            "id": "s55_w220",
            "name": "Mercedes S55 AMG (W220)",
            "make": "Mercedes-Benz",
            "model": "Klasa S",
            "variant": "S55 AMG W220",
            "years": "2002–2005",
            "engine": "5.4L V8 Kompressor M113K · 500 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa S' OR v.variant LIKE '%S55%' OR v.variant LIKE '%W220%') AND (v.variant LIKE '%S55%' OR v.power_hp >= 490)"
        },
        {
            "id": "sl55_r230",
            "name": "Mercedes SL55 AMG (R230)",
            "make": "Mercedes-Benz",
            "model": "SL",
            "variant": "SL55 AMG R230",
            "years": "2001–2008",
            "engine": "5.4L V8 Kompressor M113K · 476-517 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.model = 'SL' OR v.variant LIKE '%SL55%' OR v.variant LIKE '%R230%') AND (v.variant LIKE '%SL55%' OR v.power_hp >= 470)"
        },
        {
            "id": "cayman_987",
            "name": "Porsche Cayman (987)",
            "make": "Porsche",
            "model": "Cayman",
            "variant": "Cayman 987",
            "years": "2005–2012",
            "engine": "3.4L Flat-6 NA · 295-330 HP · RWD",
            "where": "v.make = 'Porsche' AND v.model = 'Cayman' AND (v.variant LIKE '%987%' OR (v.year >= 2005 AND v.year <= 2012))"
        },
        {
            "id": "cayman_981",
            "name": "Porsche Cayman (981)",
            "make": "Porsche",
            "model": "Cayman",
            "variant": "Cayman 981 / GT4",
            "years": "2013–2016",
            "engine": "3.4L / 3.8L Flat-6 NA · 325-385 HP · RWD",
            "where": "v.make = 'Porsche' AND v.model = 'Cayman' AND (v.variant LIKE '%981%' OR (v.year >= 2013 AND v.year <= 2016))"
        },
        {
            "id": "cayman_718",
            "name": "Porsche 718 Cayman",
            "make": "Porsche",
            "model": "718 Cayman",
            "variant": "718 Cayman",
            "years": "2016–",
            "engine": "2.5L Turbo / 4.0L NA · 350-500 HP · RWD",
            "where": "v.make = 'Porsche' AND (v.model = '718' OR v.model = 'Cayman' OR v.model = '718 Cayman') AND (v.variant LIKE '%718%' OR v.year >= 2016)"
        },
        {
            "id": "macan_gen1",
            "name": "Porsche Macan Gen 1",
            "make": "Porsche",
            "model": "Macan",
            "variant": "Macan Gen 1 (S/GTS/Turbo)",
            "years": "2014–2018",
            "engine": "3.0L / 3.6L V6 Biturbo · 340-440 HP · AWD",
            "where": "v.make = 'Porsche' AND v.model = 'Macan' AND (v.variant LIKE '%Macan%' OR (v.year >= 2014 AND v.year <= 2018))"
        },
        {
            "id": "gr_yaris",
            "name": "Toyota GR Yaris",
            "make": "Toyota",
            "model": "GR Yaris",
            "variant": "GR Yaris",
            "years": "2020–",
            "engine": "1.6L 3-cyl Turbo · 261-280 HP · AWD",
            "where": "v.make = 'Toyota' AND (v.model = 'GR Yaris' OR (v.model = 'Yaris' AND (v.variant LIKE '%GR%' OR v.power_hp >= 250)))"
        },
    ]
    STANDARD_MODELS = sorted(STANDARD_MODELS, key=lambda m: (m["make"], m["name"]))

    selected_id = request.args.get("model", "rs4_b85")
    current_model = next((m for m in STANDARD_MODELS if m["id"] == selected_id), STANDARD_MODELS[0])

    # Strict query matching this exact generation - NO loose cross-model fallback!
    sql = f"""
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
        WHERE {current_model['where']}
    """
    rows = conn.execute(sql).fetchall()
    vehicles = [dict(r) for r in rows]

    # Annotate region codes and names for mapping & filtering
    region_counts = {}
    for v in vehicles:
        reg = v.get("location_region")
        if reg and reg in REGION_NAMES:
            pass
        elif reg and reg.lower() in REGION_NAME_TO_CODE:
            reg = REGION_NAME_TO_CODE[reg.lower()]
        else:
            city = v.get("location_city")
            if city and city in CITY_TO_REGION:
                reg = CITY_TO_REGION[city]
            else:
                reg = None
                
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
        scatter_data=json.dumps(scatter_data),
        hist_labels=json.dumps(hist_labels),
        hist_counts=json.dumps(hist_counts),
        map_data=json.dumps(map_data),
        year_data=json.dumps(year_data),
    )
