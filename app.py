from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from db import get_db, init_db, make_placeholder_vin, resolve_placeholder
from datetime import datetime
import json, os, io, re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-secret-key")
app.jinja_env.filters["fromjson"] = json.loads
NOW = lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "static", "photos")
try:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
except OSError:
    pass  # Serverless read-only filesystem (e.g. Vercel)

_BACKFILLED = False

@app.before_request
def require_login():
    global _BACKFILLED
    if not _BACKFILLED:
        try:
            conn = get_db()
            backfill_vehicle_specs(conn)
            conn.close()
            _BACKFILLED = True
        except Exception as e:
            print(f"Backfill startup notice: {e}")

    if request.path.startswith("/api/") or request.path.startswith("/static/") or request.path == "/login":
        return
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_password and not session.get("logged_in"):
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == os.environ.get("ADMIN_PASSWORD"):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid password")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))


def is_plausible_vin(vin: str) -> bool:
    """Basic sanity check — see base_scraper.py for rationale."""
    if not vin or len(vin) != 17:
        return False
    vin = vin.upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        return False
    if len(set(vin)) < 5:
        return False
    if max(vin.count(c) for c in set(vin)) >= 7:
        return False
    return True


CITY_TO_REGION = {
    'Warszawa': 'PL-MZ', 'Kraków': 'PL-MA', 'Łódź': 'PL-LD', 'Wrocław': 'PL-DS',
    'Poznań': 'PL-WP', 'Gdańsk': 'PL-PM', 'Szczecin': 'PL-ZP', 'Bydgoszcz': 'PL-KP',
    'Lublin': 'PL-LU', 'Białystok': 'PL-PD', 'Katowice': 'PL-SL', 'Gdynia': 'PL-PM',
    'Częstochowa': 'PL-SL', 'Radom': 'PL-MZ', 'Toruń': 'PL-KP', 'Sosnowiec': 'PL-SL',
    'Kielce': 'PL-SK', 'Rzeszów': 'PL-PK', 'Gliwice': 'PL-SL', 'Zabrze': 'PL-SL',
    'Olsztyn': 'PL-WN', 'Bielsko-Biała': 'PL-SL', 'Bytom': 'PL-SL', 'Zielona Góra': 'PL-LB',
    'Rybnik': 'PL-SL', 'Ruda Śląska': 'PL-SL', 'Tychy': 'PL-SL', 'Gorzów Wielkopolski': 'PL-LB',
    'Dąbrowa Górnicza': 'PL-SL', 'Płock': 'PL-MZ', 'Elbląg': 'PL-WN', 'Opole': 'PL-OP',
    'Wałbrzych': 'PL-DS', 'Włocławek': 'PL-KP', 'Tarnów': 'PL-MA', 'Chorzów': 'PL-SL',
    'Koszalin': 'PL-ZP', 'Kalisz': 'PL-WP', 'Legnica': 'PL-DS', 'Grudziądz': 'PL-KP',
    'Jaworzno': 'PL-SL', 'Słupsk': 'PL-ZP', 'Jastrzębie-Zdrój': 'PL-SL', 'Nowy Sącz': 'PL-MA',
    'Jelenia Góra': 'PL-DS', 'Siedlce': 'PL-MZ', 'Mysłowice': 'PL-SL', 'Konin': 'PL-WP',
    'Piła': 'PL-WP', 'Piotrków Trybunalski': 'PL-LD', 'Łomianki': 'PL-MZ', 'Ociąż': 'PL-WP',
    'Opalenica': 'PL-WP', 'Leszno': 'PL-WP', 'Ornontowice': 'PL-SL', 'Pabianice': 'PL-LD',
    'Szamocin': 'PL-WP', 'Kazuń Polski': 'PL-MZ', 'Niepołomice': 'PL-MA', 'Nowy Dwór Gdański': 'PL-PM',
    'Piaseczno': 'PL-MZ', 'Pruszków': 'PL-MZ', 'Marki': 'PL-MZ', 'Ząbki': 'PL-MZ',
    'Otwock': 'PL-MZ', 'Legionowo': 'PL-MZ', 'Wołomin': 'PL-MZ', 'Sopot': 'PL-PM',
    'Wejherowo': 'PL-PM', 'Rumia': 'PL-PM', 'Starogard Gdański': 'PL-PM', 'Tczew': 'PL-PM',
    'Lubin': 'PL-DS', 'Głogów': 'PL-DS', 'Świdnica': 'PL-DS', 'Bolesławiec': 'PL-DS',
    'Inowrocław': 'PL-KP', 'Świecie': 'PL-KP', 'Brodnica': 'PL-KP', 'Chełm': 'PL-LU',
    'Zamość': 'PL-LU', 'Biała Podlaska': 'PL-LU', 'Puławy': 'PL-LU', 'Nowa Sól': 'PL-LB',
    'Żary': 'PL-LB', 'Zgierz': 'PL-LD', 'Skierniewice': 'PL-LD', 'Radomsko': 'PL-LD',
    'Kutno': 'PL-LD', 'Bełchatów': 'PL-LD', 'Oświęcim': 'PL-MA', 'Chrzanów': 'PL-MA',
    'Olkusz': 'PL-MA', 'Zakopane': 'PL-MA', 'Kędzierzyn-Koźle': 'PL-OP', 'Nysa': 'PL-OP',
    'Brzeg': 'PL-OP', 'Mielec': 'PL-PK', 'Przemyśl': 'PL-PK', 'Stalowa Wola': 'PL-PK',
    'Krosno': 'PL-PK', 'Jasło': 'PL-PK', 'Suwałki': 'PL-PD', 'Łomża': 'PL-PD',
    'Augustów': 'PL-PD', 'Siemianowice Śląskie': 'PL-SL', 'Tarnowskie Góry': 'PL-SL',
    'Piekary Śląskie': 'PL-SL', 'Racibórz': 'PL-SL', 'Zawiercie': 'PL-SL', 'Wodzisław Śląski': 'PL-SL',
    'Mikołów': 'PL-SL', 'Cieszyn': 'PL-SL', 'Żywiec': 'PL-SL', 'Ostrowiec Świętokrzyski': 'PL-SK',
    'Starachowice': 'PL-SK', 'Skarżysko-Kamienna': 'PL-SK', 'Sandomierz': 'PL-SK',
    'Ełk': 'PL-WN', 'Iława': 'PL-WN', 'Giżycko': 'PL-WN', 'Ostróda': 'PL-WN',
    'Ostrów Wielkopolski': 'PL-WP', 'Gniezno': 'PL-WP', 'Września': 'PL-WP', 'Swarzędz': 'PL-WP',
    'Stargard': 'PL-ZP', 'Kołobrzeg': 'PL-ZP', 'Świnoujście': 'PL-ZP', 'Szczecinek': 'PL-ZP',
    'Balice': 'PL-MA', 'Dobrzań': 'PL-ZP', 'Góra': 'PL-DS', 'Halinów': 'PL-MZ',
    'Golęczewo': 'PL-WP', 'Aleksandrów': 'PL-LD', 'Aleksandrów Łódzki': 'PL-LD',
    'Czarna': 'PL-PK', 'Stanisławów Pierwszy': 'PL-MZ', 'Garwolin': 'PL-MZ',
    'Węgrzce': 'PL-MA', 'Sochaczew': 'PL-MZ'
}

REGION_NAMES = {
    'PL-DS': 'Dolnośląskie',
    'PL-KP': 'Kujawsko-pomorskie',
    'PL-LU': 'Lubelskie',
    'PL-LB': 'Lubuskie',
    'PL-LD': 'Łódzkie',
    'PL-MA': 'Małopolskie',
    'PL-MZ': 'Mazowieckie',
    'PL-OP': 'Opolskie',
    'PL-PK': 'Podkarpackie',
    'PL-PD': 'Podlaskie',
    'PL-PM': 'Pomorskie',
    'PL-SL': 'Śląskie',
    'PL-SK': 'Świętokrzyskie',
    'PL-WN': 'Warmińsko-mazurskie',
    'PL-WP': 'Wielkopolskie',
    'PL-ZP': 'Zachodniopomorskie'
}


def infer_vehicle_specs(make, model, variant="", raw_title=""):
    """Infer known model specs for performance cars if fields are empty."""
    text = f"{make or ''} {model or ''} {variant or ''} {raw_title or ''}".lower()
    specs = {}

    if "rs4" in text:
        if "b9" in text or any(y in text for y in ["2017", "2018", "2019", "2020"]):
            specs = {"engine_cc": 2894, "engine_cyl": 6, "power_hp": 450, "body_type": "Kombi", "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}
        else: # B8 / B8.5
            specs = {"engine_cc": 4163, "engine_cyl": 8, "power_hp": 450, "body_type": "Kombi", "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "c63" in text or ("c 63" in text and ("w204" in text or "amg" in text or "mercedes" in text)):
        bt = "Kombi" if any(k in text for k in ["kombi", "t-modell", "estate", "wagon"]) else ("Coupe" if "coupe" in text else "Sedan")
        specs = {"engine_cc": 6208, "engine_cyl": 8, "power_hp": 457, "body_type": bt, "drivetrain": "RWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "e55" in text or ("e 55" in text and ("w211" in text or "amg" in text or "mercedes" in text)):
        bt = "Kombi" if any(k in text for k in ["kombi", "t-modell", "estate", "wagon"]) else "Sedan"
        specs = {"engine_cc": 5439, "engine_cyl": 8, "power_hp": 476, "body_type": bt, "drivetrain": "RWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "m4" in text:
        bt = "Kabriolet" if any(k in text for k in ["cabrio", "kabriolet", "convertible"]) else "Coupe"
        tm = "manual" if ("manual" in text or "manualna" in text) else "automatic"
        specs = {"engine_cc": 2979, "engine_cyl": 6, "power_hp": 431, "body_type": bt, "drivetrain": "RWD", "transmission": tm, "fuel_type": "petrol"}
    elif "m3" in text:
        tm = "manual" if ("manual" in text or "manualna" in text) else "automatic"
        specs = {"engine_cc": 2979, "engine_cyl": 6, "power_hp": 431, "body_type": "Sedan", "drivetrain": "RWD", "transmission": tm, "fuel_type": "petrol"}
    elif "rs3" in text:
        bt = "Sedan" if ("limousine" in text or "sedan" in text) else "Hatchback"
        specs = {"engine_cc": 2480, "engine_cyl": 5, "power_hp": 400, "body_type": bt, "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}
    elif "x3 m" in text or "x3m" in text:
        specs = {"engine_cc": 2993, "engine_cyl": 6, "power_hp": 510, "body_type": "SUV", "drivetrain": "AWD", "transmission": "automatic", "fuel_type": "petrol"}

    return specs


def backfill_vehicle_specs(conn):
    """Backfills missing body_type, engine_cc, engine_cyl, drivetrain for existing vehicles."""
    try:
        rows = conn.execute("SELECT vin, make, model, variant, body_type, engine_cc, engine_cyl, power_hp, drivetrain, transmission FROM vehicles").fetchall()
        for r in rows:
            specs = infer_vehicle_specs(r["make"], r["model"], r["variant"])
            if not specs:
                continue
            updates = []
            vals = []
            for col in ["engine_cc", "engine_cyl", "body_type", "drivetrain", "power_hp", "transmission"]:
                val = r[col] if col in r.keys() else None
                if specs.get(col) and (val is None or val == "" or val == 0):
                    updates.append(f"{col} = ?")
                    vals.append(specs[col])
            if updates:
                vals.append(r["vin"])
                conn.execute(f"UPDATE vehicles SET {', '.join(updates)}, updated_at = datetime('now') WHERE vin = ?", vals)
        conn.commit()
    except Exception as e:
        print(f"Backfill error: {e}")


def _approve_listing(conn, listing, overrides=None):
    """Upsert vehicle + insert observation + mark pending row approved.

    overrides: dict of form fields that take precedence over listing values
               (used by the manual review form). Pass None for auto-approve.
    Returns the VIN string used.
    """
    overrides = overrides or {}

    vin = (overrides.get("vin") or listing["vin"] or "").strip().upper()
    if not vin or len(vin) != 17:
        vin = make_placeholder_vin(
            listing["source"] or "olx",
            listing["source_listing_id"] or str(listing["id"])
        )

    def _get(key, cast=None):
        val = overrides.get(key)
        if not val and key in listing.keys():
            val = listing[key]
        if val is None or val == "":
            return None
        return cast(val) if cast else val

    raw_title = listing["raw_title"] if "raw_title" in listing.keys() else ""
    inferred = infer_vehicle_specs(
        _get("make"), _get("model"), _get("variant"), raw_title
    )
    final_body_type    = _get("body_type") or inferred.get("body_type")
    final_engine_cc    = _get("engine_cc", int) or inferred.get("engine_cc")
    final_engine_cyl   = _get("engine_cyl", int) or inferred.get("engine_cyl")
    final_power_hp     = _get("power_hp", int) or inferred.get("power_hp")
    final_drivetrain   = _get("drivetrain") or inferred.get("drivetrain")
    final_transmission = _get("transmission") or inferred.get("transmission")

    conn.execute("""
        INSERT INTO vehicles
          (vin, make, model, variant, year, body_type,
           engine_cc, engine_cyl, power_hp, drivetrain, transmission,
           color_ext, vin_status, source_method)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vin) DO UPDATE SET
          make        = COALESCE(excluded.make, make),
          model       = COALESCE(excluded.model, model),
          variant     = COALESCE(excluded.variant, variant),
          power_hp    = COALESCE(excluded.power_hp, power_hp),
          engine_cc   = COALESCE(excluded.engine_cc, engine_cc),
          engine_cyl  = COALESCE(excluded.engine_cyl, engine_cyl),
          body_type   = COALESCE(excluded.body_type, body_type),
          drivetrain  = COALESCE(excluded.drivetrain, drivetrain),
          transmission= COALESCE(excluded.transmission, transmission),
          updated_at  = datetime('now')
    """, (
        vin,
        _get("make") or "Unknown",
        _get("model") or "Unknown",
        _get("variant"),
        int(overrides["year"])      if overrides.get("year")      else (listing["year"] or 0),
        final_body_type,
        final_engine_cc,
        final_engine_cyl,
        final_power_hp,
        final_drivetrain,
        final_transmission,
        _get("color_ext"),
        "placeholder" if vin.startswith("UNVERIFIED") else "unverified",
        f"scraper-{listing['source']}",
    ))

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
        float(overrides["price_pln"])  if overrides.get("price_pln")  else listing["price_pln"],
        int(overrides["mileage_km"])   if overrides.get("mileage_km") else listing["mileage_km"],
        overrides.get("location_city") or listing["location_city"],
        overrides.get("seller_type")   or listing["seller_type"] or "private",
        overrides.get("seller_name")   or listing["seller_name"],
        listing["scraped_at"], listing["scraped_at"],
        f"scraper-{listing['source']}",
        overrides.get("notes"),
    ))

    conn.execute("""
        UPDATE pending_listings
        SET status='approved', reviewed_at=datetime('now'), review_notes=?
        WHERE id=?
    """, (overrides.get("notes"), listing["id"]))

    local_photo = listing["local_photo"] if "local_photo" in listing.keys() else None
    if local_photo:
        conn.execute(
            "UPDATE vehicles SET photo=? WHERE vin=? AND (photo IS NULL OR photo='')",
            (local_photo, vin)
        )

    return vin


def check_storage_limit(conn) -> bool:
    """Returns True if we're under the estimated 7.5GB limit."""
    try:
        c1 = conn.execute("SELECT COUNT(local_photo) FROM pending_listings WHERE local_photo IS NOT NULL").fetchone()[0]
        c2 = conn.execute("SELECT COUNT(photo) FROM vehicles WHERE photo IS NOT NULL AND photo != ''").fetchone()[0]
        total_photos = c1 + c2
        # Estimate 20KB per photo (400px, 60% quality)
        estimated_gb = (total_photos * 20.0) / 1024 / 1024
        if estimated_gb > 5.0:
            print("WARNING: Storage exceeded 5GB limit!")
        return estimated_gb < 7.5
    except Exception:
        return True

def save_photo(url: str, filename: str, max_width: int = 400, quality: int = 60):
    """Download url, compress to JPEG, save to Cloudflare R2 (or local fallback)."""
    if not url:
        return None
        
    conn = get_db()
    under_limit = check_storage_limit(conn)
    conn.close()
    if not under_limit:
        print("Storage limit of 7.5GB exceeded, skipping photo upload.")
        return None

    try:
        from PIL import Image
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, timeout=12, impersonate="chrome")
        if resp.status_code != 200:
            return None
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
            
        endpoint = os.environ.get("R2_ENDPOINT_URL")
        bucket = os.environ.get("R2_BUCKET_NAME")
        
        if endpoint and bucket:
            import boto3
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=quality, optimize=True)
            buffer.seek(0)
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
                region_name="auto"
            )
            s3.upload_fileobj(buffer, bucket, f"photos/{filename}", ExtraArgs={'ContentType': 'image/jpeg'})
            return f"photos/{filename}"
        else:
            path = os.path.join(PHOTOS_DIR, filename)
            img.save(path, "JPEG", quality=quality, optimize=True)
            return f"photos/{filename}"
    except Exception as e:
        print(f"Error saving photo: {e}")
        return None

@app.route("/media/<path:filename>")
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

    # Filters from interactive charts / query params
    filter_region = request.args.get("region", "").strip()
    filter_make = request.args.get("make", "").strip()
    filter_price = request.args.get("price", "").strip()

    recent_sql = """
        SELECT v.vin, v.make, v.model, v.variant, v.year, v.power_hp, v.vin_status, v.photo,
               o.price_pln, o.mileage_km, o.location_city, o.source, o.source_method, o.observed_at, o.source_url
        FROM listing_observations o
        JOIN vehicles v ON o.vin = v.vin
    """
    wheres = []
    params = []
    active_filter = None

    if filter_make:
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
            wheres.append(f"o.location_city IN ({placeholders})")
            params.extend(cities_in_region)
        else:
            wheres.append("1=0")
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

    cities = conn.execute("SELECT location_city, COUNT(*) as cnt FROM listing_observations WHERE location_city IS NOT NULL GROUP BY location_city").fetchall()
    region_counts = {}
    for r in cities:
        reg = CITY_TO_REGION.get(r["location_city"], "PL-MZ")
        region_counts[reg] = region_counts.get(reg, 0) + r["cnt"]
    
    map_data = [["State", "Observations"]] + [[k, v] for k, v in region_counts.items()]

    conn.close()
    return render_template("dashboard.html",
        stats=stats, recent=recent,
        makes_dist=json.dumps([dict(r) for r in makes_dist]),
        price_ranges=json.dumps([dict(r) for r in price_ranges]),
        weekly=json.dumps([dict(r) for r in weekly]),
        sources=json.dumps([dict(r) for r in sources]),
        map_data=json.dumps(map_data),
        active_filter=active_filter
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODEL ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/models")
def model_analytics():
    conn = get_db()

    STANDARD_MODELS = [
        {
            "id": "rs3_8v",
            "name": "Audi RS3 (8V)",
            "make": "Audi",
            "model": "RS3",
            "variant": "8V",
            "years": "2015–2020",
            "engine": "2.5L TFSI · 400 HP · Quattro",
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
            "years": "2017–2019",
            "engine": "2.9L V6 Biturbo · 450 HP · Quattro",
            "where": "v.make = 'Audi' AND v.model = 'RS4' AND (v.variant LIKE '%B9%' OR (v.year >= 2017 AND v.year <= 2020)) AND (v.variant NOT LIKE '%B8%' AND (v.year >= 2017 OR v.year IS NULL))"
        },
        {
            "id": "c63_w204",
            "name": "Mercedes C63 AMG",
            "make": "Mercedes-Benz",
            "model": "Klasa C",
            "variant": "W204 C63 AMG",
            "years": "2008–2015",
            "engine": "6.2L V8 M156 · 457 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%W204%' OR v.variant LIKE '%C63%' OR v.variant LIKE '%C 63%' OR (v.model = 'Klasa C' AND (v.power_hp >= 450 OR v.engine_cc > 6000)))"
        },
        {
            "id": "e55_w211",
            "name": "Mercedes E55 AMG",
            "make": "Mercedes-Benz",
            "model": "Klasa E",
            "variant": "W211 E55 AMG",
            "years": "2003–2006",
            "engine": "5.4L V8 Kompressor · 476 HP · RWD",
            "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%W211%' OR v.variant LIKE '%E55%' OR v.variant LIKE '%E 55%' OR (v.model = 'Klasa E' AND (v.power_hp >= 460 OR v.engine_cc = 5439)))"
        },
        {
            "id": "m4_f82",
            "name": "BMW M4 (F82)",
            "make": "BMW",
            "model": "M4",
            "variant": "F82",
            "years": "2014–2020",
            "engine": "3.0L Twin-Turbo S55 · 431 HP · RWD",
            "where": "v.make = 'BMW' AND (v.model = 'M4' OR v.variant LIKE '%F82%') AND (v.year >= 2014 AND v.year <= 2020)"
        },
        {
            "id": "x3_m_f97",
            "name": "BMW X3 M (F97)",
            "make": "BMW",
            "model": "X3 M",
            "variant": "F97",
            "years": "2019–2024",
            "engine": "3.0L Twin-Turbo S58 · 510 HP · AWD",
            "where": "v.make = 'BMW' AND (v.model = 'X3 M' OR v.model = 'X3M' OR (v.model = 'X3' AND (v.variant LIKE '%M%' OR v.variant LIKE '%F97%'))) AND (v.year >= 2019 AND v.year <= 2024)"
        },
    ]

    selected_id = request.args.get("model", "rs4_b85")
    current_model = next((m for m in STANDARD_MODELS if m["id"] == selected_id), STANDARD_MODELS[0])

    # Strict query matching this exact generation - NO loose cross-model fallback!
    sql = f"""
        SELECT v.*, 
               o.price_pln, o.mileage_km, o.location_city, o.observed_at, o.source_url, o.title
        FROM vehicles v
        LEFT JOIN (
            SELECT vin, price_pln, mileage_km, location_city, observed_at, source_url, title,
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
        city = v.get("location_city")
        if city:
            reg = CITY_TO_REGION.get(city, "PL-MZ")
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


# ─────────────────────────────────────────────────────────────────────────────
# VEHICLES LIST
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicles")
def vehicles_list():
    conn   = get_db()
    q      = request.args.get("q", "").strip()
    make   = request.args.get("make", "")
    status = request.args.get("status", "")
    region = request.args.get("region", "").strip()
    sort   = request.args.get("sort", "updated_at")

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
    if region:
        cities_in_region = [c for c, r in CITY_TO_REGION.items() if r == region]
        if cities_in_region:
            placeholders = ",".join("?" for _ in cities_in_region)
            wheres.append(f"o.location_city IN ({placeholders})")
            params.extend(cities_in_region)
        else:
            wheres.append("1=0")

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
        q=q, selected_make=make, status=status, sort=sort,
        selected_region=region, regions=REGION_NAMES)


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

@app.route("/vehicle/<path:vin>/update_status", methods=["POST"])
def update_status(vin):
    new_status = request.form.get("vin_status", "unverified")
    conn = get_db()
    conn.execute("UPDATE vehicles SET vin_status=? WHERE vin=?", (new_status, vin))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# TAGS — add / delete from vehicle detail page
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicle/<path:vin>/add_tag", methods=["POST"])
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
    return redirect(url_for("vehicle_detail", vin=vin))


@app.route("/vehicle/<path:vin>/delete_tag", methods=["POST"])
def delete_tag(vin):
    tag = request.form.get("tag", "").strip()
    if tag:
        conn = get_db()
        conn.execute("DELETE FROM tags WHERE vin=? AND tag=?", (vin, tag))
        conn.commit()
        conn.close()
    return redirect(url_for("vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE VEHICLE — requires typing the VIN to confirm
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/vehicle/<path:vin>/delete", methods=["POST"])
def delete_vehicle(vin):
    confirm = request.form.get("confirm_vin", "").strip().upper()
    if confirm != vin.upper():
        return redirect(url_for("vehicle_detail", vin=vin) + "?delete_error=1")
    conn = get_db()
    conn.execute("DELETE FROM listing_observations WHERE vin=?", (vin,))
    conn.execute("DELETE FROM condition_reports WHERE vin=?", (vin,))
    conn.execute("DELETE FROM tags WHERE vin=?", (vin,))
    conn.execute("DELETE FROM vin_correction_log WHERE old_vin=? OR new_vin=?", (vin, vin))
    conn.execute("DELETE FROM vehicles WHERE vin=?", (vin,))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicles_list"))


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

def check_api_token():
    token = os.environ.get("API_TOKEN")
    if token:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.split(" ")[1] != token:
            return jsonify({"error": "Unauthorized"}), 401
    return None

@app.route("/api/ingest", methods=["POST"])
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

@app.route("/api/mark_removed", methods=["POST"])
def api_mark_removed():
    """Called by scrapers after each run with the listing IDs they observed.

    Any active observation for this source+make+model that is NOT in seen_ids
    gets removed_at stamped — meaning the listing disappeared (likely sold).
    """
    if err := check_api_token(): return err
    
    p        = request.get_json(force=True)
    source   = p.get("source")
    make     = p.get("make")
    model    = p.get("model")
    seen_ids = p.get("seen_ids", [])
    if not source or not seen_ids:
        return jsonify({"marked": 0})
    conn = get_db()
    
    # 1. Fetch active observations for this source/make/model
    active_rows = conn.execute("""
        SELECT source_listing_id 
        FROM listing_observations 
        WHERE source = ? 
          AND removed_at IS NULL
          AND vin IN (SELECT vin FROM vehicles WHERE make = ? AND model = ?)
    """, (source, make, model)).fetchall()
    
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
    if err := check_api_token(): return err
    
    p      = request.get_json(force=True)
    source = p.get("source", "olx")
    sid    = p.get("source_listing_id")
    vin    = (p.get("vin") or "").strip().upper()
    vc     = p.get("vin_confidence", "none")

    conn = get_db()
    try:
        cur = conn.execute("""
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
            source, sid, p.get("source_url"),
            p.get("raw_title"), p.get("raw_description"),
            json.dumps(p.get("photos", [])),
            p.get("make"), p.get("model"), p.get("variant"),
            p.get("year"), p.get("body_type"),
            p.get("engine_cc"), p.get("power_hp"), p.get("fuel_type"),
            p.get("drivetrain"), p.get("transmission"),
            p.get("color_ext"), p.get("doors"),
            p.get("price_pln"), p.get("price_eur"), p.get("mileage_km"),
            p.get("location_city"), p.get("location_region"),
            p.get("seller_type"), p.get("seller_name"),
            vin or None, vc, 1,
        ))
        conn.commit()

        # ── Duplicate path ────────────────────────────────────────────────────
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT * FROM pending_listings WHERE source=? AND source_listing_id=?",
                (source, sid)
            ).fetchone()
            if existing and existing["status"] == "approved":
                new_price = p.get("price_pln")
                old_price = existing["price_pln"]
                if new_price and old_price and abs(float(new_price) - float(old_price)) > 500:
                    # Price changed on an already-approved listing → new observation
                    existing_vin = existing["vin"]
                    if existing_vin:
                        conn.execute("""
                            INSERT INTO listing_observations
                              (vin, source, source_listing_id, source_url, title,
                               price_pln, mileage_km, location_city,
                               seller_type, first_seen_at, observed_at, source_method)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            existing_vin, source, sid,
                            existing["source_url"], existing["raw_title"],
                            float(new_price),
                            p.get("mileage_km") or existing["mileage_km"],
                            p.get("location_city") or existing["location_city"],
                            existing["seller_type"] or "private",
                            NOW(), NOW(),
                            f"scraper-{source}",
                        ))
                        conn.commit()
                        conn.close()
                        return jsonify({"status": "ok", "id": existing["id"],
                                        "tag": "price_updated"})
            conn.close()
            return jsonify({"status": "ok", "id": 0, "tag": "duplicate"})

        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

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
                "SELECT vin FROM vehicles WHERE vin=?", (vin,)
            ).fetchone()
            if known:
                conn.execute("""
                    INSERT INTO listing_observations
                      (vin, source, source_listing_id, source_url, title,
                       price_pln, mileage_km, location_city,
                       seller_type, first_seen_at, observed_at, source_method)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    vin, source, sid, p.get("source_url"), p.get("raw_title"),
                    p.get("price_pln"), p.get("mileage_km"), p.get("location_city"),
                    p.get("seller_type") or "private",
                    NOW(), NOW(), f"scraper-{source}",
                ))
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
        return redirect(url_for("review_detail", pid=next_p["id"]))
    return redirect(url_for("review_queue"))

@app.route("/review/reject_all_pending")
def review_reject_all_pending():
    conn = get_db()
    conn.execute(
        "UPDATE pending_listings SET status='rejected', reviewed_at=datetime('now') WHERE status='pending'"
    )
    conn.commit()
    conn.close()
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review_queue"))

@app.route("/review/clear_rejected")
def review_clear_rejected():
    conn = get_db()
    conn.execute("DELETE FROM pending_listings WHERE status='rejected'")
    conn.commit()
    conn.close()
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review_queue"))


@app.route("/review/bulk_approve", methods=["POST"])
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
            except Exception:
                pass
        conn.commit()
        conn.close()
    
    if request.args.get("ajax") == "1":
        return {"status": "success"}
    return redirect(url_for("review_queue"))


@app.route("/review/bulk_reject", methods=["POST"])
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
    
    if request.args.get("ajax") == "1":
        conn.close()
        return {"status": "success", "id": pid}

    # Auto-advance to next pending
    next_p = conn.execute(
        "SELECT id FROM pending_listings WHERE status='pending' ORDER BY scraped_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if next_p:
        return redirect(url_for("review_detail", pid=next_p["id"]))
    return redirect(url_for("review_queue"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5555)
