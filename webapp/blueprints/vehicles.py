import json
import time
from datetime import datetime
from urllib.parse import urlencode
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from db import get_db, resolve_placeholder
from webapp import invalidate_notifications
from webapp.helpers import (CC_MAX, CC_MIN, CC_STEP, FUELS, NOW, WRONG_MODEL, WRONG_MODEL_NOTE, car_flags_sql, damaged_ad_sql,
                            engine_filter, safe_float, safe_int, script_json)
from webapp.regions import CITY_TO_REGION, REGION_NAMES
from webapp.services import verification
from webapp.services.photos import store_photo
from webapp.services.plates import card_plates, normalize_plate, plate_card_hints, plate_check_plan
from validation import MIN_FIRST_REGISTRATION_YEAR, OVERSEAS_ORIGINS

bp = Blueprint("vehicles", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# VEHICLES LIST
# ─────────────────────────────────────────────────────────────────────────────

PER_PAGE = 50

# "Pochodzenie" choices: the origin markets each leaves out. A car of unknown origin (most) passes.
ORIGIN_FILTERS = {
    "no_usa":  ("Bez USA i Kanady", OVERSEAS_ORIGINS),
    "europe":  ("Bez aut spoza Europy", (*OVERSEAS_ORIGINS, "Japonia", "Zatoka Perska")),
}
MILEAGE_MAX = 2_000_000
# The query string keys of the list's filters and sort, kept by the page links
LIST_ARGS = ("id", "q", "make", "status", "region", "source", "sort", "fuel", "cc_from", "cc_to",
             "origin", "km_from", "km_to", "reg_from", "reg_to")


def latest_mileage_sql(alias):
    """SQL expression: the mileage the car's newest sighting gives (what its ad says now), NULL if
    none gives one. A few index rows per car (idx_obs_vin_observed)."""
    return (f"(SELECT x.mileage_km FROM listing_observations x WHERE x.vin = {alias}.vin AND x.mileage_km > 0 "
            "ORDER BY x.observed_at DESC LIMIT 1)")


def _bounded_int(args, key, lo, hi):
    """args[key] as an int within [lo, hi]; None when empty, not a number or outside."""
    try:
        value = int(str(args.get(key) or "").replace(" ", ""))
    except ValueError:
        return None
    return value if lo <= value <= hi else None


def history_filter(args):
    """Origin, mileage (km, from / to) and first registration (year, from / to) chosen in the
    query string. Returns (chosen, sql_conditions, params); chosen holds the valid values for the
    form. Like the engine filter, a car without the data does not pass a filter on it (except
    origin, where an unknown one passes: most cars have none)."""
    origin = args.get("origin", "")
    origin = origin if origin in ORIGIN_FILTERS else ""
    year_now = datetime.now().year
    chosen = {"origin": origin,
              "km_from": _bounded_int(args, "km_from", 0, MILEAGE_MAX),
              "km_to": _bounded_int(args, "km_to", 0, MILEAGE_MAX),
              "reg_from": _bounded_int(args, "reg_from", MIN_FIRST_REGISTRATION_YEAR, year_now),
              "reg_to": _bounded_int(args, "reg_to", MIN_FIRST_REGISTRATION_YEAR, year_now)}
    conds, params = [], []
    if origin:
        left_out = ORIGIN_FILTERS[origin][1]
        conds.append(f"COALESCE(v.origin_market, '') NOT IN ({','.join('?' * len(left_out))})")
        params += left_out
    mileage = latest_mileage_sql("v")
    if chosen["km_from"] is not None:
        conds.append(f"{mileage} >= ?"); params.append(chosen["km_from"])
    if chosen["km_to"] is not None:
        conds.append(f"{mileage} <= ?"); params.append(chosen["km_to"])
    # first_registration_date is YYYY-MM-DD, so years compare as strings
    if chosen["reg_from"] is not None:
        conds.append("v.first_registration_date >= ?"); params.append(f"{chosen['reg_from']}-01-01")
    if chosen["reg_to"] is not None:
        conds.append("v.first_registration_date < ?"); params.append(f"{chosen['reg_to'] + 1}-01-01")
    return chosen, conds, params


@bp.route("/vehicles")
def vehicles_list():
    return _vehicles_page(favorites_only=False)


@bp.route("/favorites")
def favorites_list():
    """The cars marked with the star: the /vehicles list limited to them, newest favourite first."""
    return _vehicles_page(favorites_only=True)


@bp.route("/api/favorite", methods=["POST"])
def api_favorite():
    """Body {"vin", "on"}: add the car to the favourites or take it off. Returns {"favorite": bool}."""
    data = request.get_json(silent=True) or {}
    vin, on = str(data.get("vin") or "").strip(), bool(data.get("on"))
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM vehicles WHERE vin = ?", (vin,)).fetchone():
            return jsonify({"error": "Nie ma takiego auta"}), 404
        if on:
            conn.execute("INSERT OR IGNORE INTO favorites (vin) VALUES (?)", (vin,))
        else:
            conn.execute("DELETE FROM favorites WHERE vin = ?", (vin,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"favorite": on})


def _vehicles_page(favorites_only: bool):
    conn   = get_db()
    q      = request.args.get("q", "").strip()
    # The car's ID (shown as #123 before the VIN); a leading # is allowed
    car_id = request.args.get("id", "").strip().lstrip("#").strip()
    make   = request.args.get("make", "")
    status = request.args.get("status", "")
    region = request.args.get("region", "").strip()
    source = request.args.get("source", "")
    source = source if source in ("olx", "otomoto", "autoplac") else ""
    sort   = request.args.get("sort", "fav_added" if favorites_only else "last_seen")
    page   = max(request.args.get("page", 1, type=int) or 1, 1)

    fuel, cc_from, cc_to, engine_conds, engine_params = engine_filter(request.args)
    history, history_conds, history_params = history_filter(request.args)
    # The VIN base lists every car we have. Cars whose sightings are left out of the market data
    # (dealer stock, an import offer, a wrong model) are listed too, marked with the reason.
    wheres, params = [*engine_conds, *history_conds], [*engine_params, *history_params]
    if favorites_only:
        wheres.append("v.vin IN (SELECT vin FROM favorites)")
    if car_id:
        # Not a number: no car has that ID, so the list is empty rather than unfiltered
        wheres.append("v.car_id = ?"); params.append(int(car_id) if car_id.isdigit() else -1)
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
        cond = "(lo.location_region = ?"
        rparams = [region]
        if cities_in_region:
            cond += f" OR lo.location_city IN ({','.join('?' for _ in cities_in_region)})"
            rparams += cities_in_region
        cond += ")"
        wheres.append(f"v.vin IN (SELECT lo.vin FROM listing_observations lo WHERE {cond})")
        params += rparams

    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""

    # The page's 50 cars are picked first, with a sort key that costs a few index rows per car
    # (idx_obs_vin_observed); their sighting summary, tags and markers are computed for those 50
    # only. Summarising every car's sightings on each page view read ~75k rows.
    usable = "x.vin = v.vin"
    sort_map = {
        # ORDER BY ... LIMIT 1, not MAX(): with the extra condition MAX() reads every sighting
        "last_seen":  (f"(SELECT x.observed_at FROM listing_observations x WHERE {usable} "
                       "ORDER BY x.observed_at DESC LIMIT 1)",
                       "sort_key DESC, v.updated_at DESC"),
        "updated_at": ("NULL", "v.updated_at DESC"),
        "year_desc":  ("NULL", "v.year DESC"),
        "year_asc":   ("NULL", "v.year ASC"),
        "power":      ("NULL", "v.power_hp DESC"),
        "obs":        (f"(SELECT COUNT(*) FROM listing_observations x WHERE {usable})", "sort_key DESC"),
        "price":      (f"(SELECT MIN(x.price_pln) FROM listing_observations x WHERE {usable})", "sort_key ASC NULLS LAST"),
        "mileage":    (latest_mileage_sql("v"), "sort_key ASC NULLS LAST"),
        "fav_added":  ("(SELECT f.created_at FROM favorites f WHERE f.vin = v.vin)", "sort_key DESC NULLS LAST, v.updated_at DESC"),
    }
    sort_key, order_sql = sort_map.get(sort, sort_map["fav_added" if favorites_only else "last_seen"])

    total = conn.execute(f"SELECT COUNT(*) FROM vehicles v{where_sql}", params).fetchone()[0]
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(page, pages)
    vehicles = conn.execute(f"""
        WITH page AS (
            SELECT v.*, {sort_key} AS sort_key FROM vehicles v{where_sql}
            ORDER BY {order_sql} LIMIT ? OFFSET ?
        )
        SELECT p.*, o.obs_count, o.ad_count, o.min_price, o.max_price, o.last_observed, o.active_ads, o.sources,
               (SELECT GROUP_CONCAT(t.tag) FROM tags t WHERE t.vin = p.vin) AS tags,
               {latest_mileage_sql("p")} AS mileage,
               -- Why the car is out of the market data: set only when none of its sightings counts
               CASE WHEN NOT EXISTS (SELECT 1 FROM listing_observations u WHERE u.vin = p.vin AND u.excluded_reason IS NULL)
                    THEN (SELECT e.excluded_reason FROM listing_observations e WHERE e.vin = p.vin
                          AND e.excluded_reason IS NOT NULL   -- a wrong model first, dealer stock last
                          ORDER BY e.excluded_reason LIKE 'dealer%', e.excluded_reason = 'import_offer'
                          LIMIT 1) END AS left_out,
               {car_flags_sql("p")}
        FROM page p
        LEFT JOIN (
            SELECT vin,
                   COUNT(*)                          AS obs_count,
                   COUNT(DISTINCT source_listing_id) AS ad_count,
                   MIN(price_pln)                    AS min_price,
                   MAX(price_pln)                    AS max_price,
                   MAX(observed_at)                  AS last_observed,
                   SUM(CASE WHEN removed_at IS NULL THEN 1 ELSE 0 END) AS active_ads,
                   GROUP_CONCAT(DISTINCT source)     AS sources
            FROM listing_observations
            WHERE vin IN (SELECT vin FROM page)
            GROUP BY vin
        ) o ON o.vin = p.vin
        ORDER BY {order_sql.replace("v.", "p.")}
    """, [*params, PER_PAGE, (page - 1) * PER_PAGE]).fetchall()
    makes    = conn.execute("SELECT DISTINCT make FROM vehicles ORDER BY make").fetchall()
    conn.close()
    chosen = {k: v for k in LIST_ARGS if (v := request.args.get(k, "").strip())}
    return render_template("vehicles.html",
        vehicles=vehicles, makes=[m["make"] for m in makes],
        q=q, car_id=car_id, selected_make=make, status=status, sort=sort,
        selected_region=region, regions=REGION_NAMES, source=source,
        fuel=fuel, cc_from=cc_from, cc_to=cc_to, fuels=FUELS, cc_min=CC_MIN, cc_max=CC_MAX, cc_step=CC_STEP,
        history=history, origin_filters=ORIGIN_FILTERS,
        reg_years=range(datetime.now().year, MIN_FIRST_REGISTRATION_YEAR - 1, -1),
        # the filters as a query string, for the page links and (without the region) its ✕
        filter_qs=urlencode(chosen),
        clear_region_qs=urlencode({k: v for k, v in chosen.items() if k != "region"}),
        page=page, pages=pages, total=total,
        favorites_only=favorites_only, base_path="/favorites" if favorites_only else "/vehicles")


# ─────────────────────────────────────────────────────────────────────────────
# VIN DETAIL
# ─────────────────────────────────────────────────────────────────────────────

def ad_summaries(observations):
    """The car's ads for its page, from its observations (newest first): one entry per ad with its
    first and last sighting, current and first price, and only the sightings where price, mileage
    or plate changed (every scraper run adds one); live ads first. Also the observations without an
    ad id."""
    groups, ungrouped = {}, []
    for o in observations:
        if o["source_listing_id"]:
            groups.setdefault((o["source"], o["source_listing_id"]), []).append(o)
        else:
            ungrouped.append(o)
    ads = []
    for (source, listing_id), obs in groups.items():
        oldest, newest = obs[-1], obs[0]
        changes, last = [], None
        for o in reversed(obs):
            key = (o["price_pln"], o["mileage_km"], o["registration_plate"])
            if key != last:
                changes.append(o)
                last = key
        ads.append({
            "source": source, "listing_id": listing_id, "newest": newest,
            "url": next((o["source_url"] for o in obs if o["source_url"]), None),
            "first_seen": (oldest["first_seen_at"] or oldest["observed_at"] or "")[:10],
            "last_seen": (newest["last_seen_at"] or newest["observed_at"] or "")[:10],
            "removed_at": (newest["removed_at"] or "")[:10],
            "price": next((o["price_pln"] for o in obs if o["price_pln"]), None),
            "first_price": next((o["price_pln"] for o in reversed(obs) if o["price_pln"]), None),
            "changes": changes[::-1], "observations": obs,
        })
    ads.sort(key=lambda a: a["last_seen"], reverse=True)
    ads.sort(key=lambda a: bool(a["removed_at"]))
    return ads, ungrouped


def to_check_context(conn, vin, message=None, ok=True, needs_force=False):
    """What waits for a person on the car's page: its pending /plates card (with the plate the rules
    suggest and the hints why CEPiK may not know the car) and its open "Do sprawdzenia" notes."""
    card = conn.execute("""
        SELECT id, detected_plate, crop_path, photo_url, confidence, created_at
        FROM plate_review_queue WHERE vin = ? AND status = 'pending' ORDER BY id DESC LIMIT 1
    """, (vin,)).fetchone()
    if card:
        card = dict(card)
        plan = plate_check_plan(conn, vin).get(card["id"])
        reading = normalize_plate(card["detected_plate"])
        card["hints"] = plate_card_hints(plan) if plan else []
        card["checks_left"] = len(plan["todo"]) if plan else 0
        card["suggested"] = (card_plates(reading, plan["car_plate"] if plan else None)[:1] or [reading])[0]
    return {"vin": vin, "card": card, "notes": verification.review_notes(conn, vin=vin),
            "topics": verification.NOTE_TOPICS, "message": message, "ok": ok, "needs_force": needs_force}


@bp.route("/vehicle/<path:vin>/to_check")
def vehicle_to_check(vin):
    """The "Do sprawdzenia" panel of the car's page (loaded by htmx after the page)."""
    conn = get_db()
    try:
        return render_template("_vehicle_to_check.html", **to_check_context(conn, vin))
    finally:
        conn.close()


@bp.route("/vehicle/<path:vin>/plate_card", methods=["POST"])
def vehicle_plate_card(vin):
    """Approve or reject the car's /plates card from its page, as on /plates; answers with the
    panel again."""
    from webapp.blueprints.plates import review_card
    card_id = safe_int(request.form.get("card_id"))
    conn = get_db()
    try:
        row = conn.execute("SELECT vin FROM plate_review_queue WHERE id = ?", (card_id,)).fetchone()
        if not row or row["vin"] != vin:
            return "Ta karta nie należy do tego auta", 400
        payload, status = review_card(conn, card_id, request.form.get("action"), request.form.get("plate"),
                                      request.form.get("force") == "1")
        invalidate_notifications()
        if status == 200:
            message = (f"Tablica {payload['plate']} zatwierdzona." if payload["action"] == "approve"
                       else "Karta odrzucona" + (f": tablica {payload['removed']} usunięta z auta." if payload.get("removed") else "."))
        else:
            message = payload.get("message")
        return render_template("_vehicle_to_check.html", **to_check_context(
            conn, vin, message=message, ok=status == 200, needs_force=payload.get("status") == "needs_confirmation"))
    finally:
        conn.close()


@bp.route("/vehicle/<path:vin>")
def vehicle_detail(vin):
    conn = get_db()
    vehicle = conn.execute("SELECT v.*, " + car_flags_sql("v") + " FROM vehicles v WHERE v.vin=?", (vin,)).fetchone()
    if not vehicle:
        conn.close()
        return "Nie znaleziono VIN-u", 404

    observations = conn.execute("""
        SELECT * FROM listing_observations
        WHERE vin=? ORDER BY observed_at DESC
    """, (vin,)).fetchall()
    # Hidden as a wrong model (the button at the bottom of the page): why, for the banner
    wrong_model = None
    if any(o["excluded_reason"] == WRONG_MODEL for o in observations):
        note = conn.execute("SELECT review_notes FROM pending_listings WHERE vin = ? AND status = 'rejected' "
                            "AND review_notes LIKE ? LIMIT 1", (vin, WRONG_MODEL_NOTE + "%")).fetchone()
        wrong_model = (note["review_notes"][len(WRONG_MODEL_NOTE):] if note else "") or "bez opisu"
    # Why the car is marked damaged (the portal's mark, or a quote from the ad), for the card
    # that lets the user dismiss a wrong one
    damage_marks = verification.damage_marks(conn, vin)
    sold_damaged = conn.execute(
        "SELECT 1 FROM listing_observations x WHERE x.vin = ? AND " + damaged_ad_sql("x") + " LIMIT 1", (vin,)).fetchone() is not None

    ads, ungrouped = ad_summaries(observations)

    conditions = conn.execute(
        "SELECT * FROM condition_reports WHERE vin=? ORDER BY report_date DESC, id DESC", (vin,)).fetchall()
    damage_reports = [c for c in conditions if c["accident_free"] == 0]

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
    if orig:
        photos = json.loads(orig["photos"]) if orig["photos"] else []
        equipment = json.loads(orig["equipment"]) if orig["equipment"] else []
        raw_desc = orig["raw_description"]
    # Bielik's analysis of the car, made from all its ads (enrich_with_bielik.py); until the car has
    # one, that of its newest ad
    source = vehicle if vehicle["ai_processed_at"] else orig
    ai_data = {"summary": None, "equipment": [], "reasoning": None, "market": None,
               "interior": vehicle["color_int"], "has_conflict": False,
               "ad_count": vehicle["ai_ad_count"] if source is vehicle else 1}
    if source:
        ai_data.update(summary=source["ai_summary"], reasoning=source["ai_reasoning"],
                       market=source["ai_suggested_market"], has_conflict=bool(source["ai_conflict"]))
        try:
            ai_data["equipment"] = json.loads(source["ai_equipment"] or "[]")
        except ValueError:
            pass
        if source["ai_interior_color"]:
            ai_data["interior"] = source["ai_interior_color"]

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
    # From North America: almost always a damaged car, so its page points to the auctions. Only the
    # origin market tells: where the VIN says it was built does not (every X3 is built in the USA,
    # also those sold in Europe).
    north_american = vehicle["origin_market"] in OVERSEAS_ORIGINS
    return render_template("vehicle.html",
        vehicle=vehicle,
        north_american=north_american,
        wrong_model=wrong_model,
        damage_marks=damage_marks,
        sold_damaged=sold_damaged,
        damage_reports=damage_reports,
        ads=ads,
        ungrouped=ungrouped,
        observations=observations,
        conditions=conditions,
        tags=tags,
        corrections=corrections,
        price_timeline=script_json([dict(r) for r in price_timeline]),
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

DAMAGE_PHOTO_MAX_BYTES = 4 * 1024 * 1024  # Vercel refuses request bodies over 4.5 MB


@bp.route("/vehicle/<path:vin>/add_condition", methods=["POST"])
def add_condition(vin):
    """A condition report: an inspection, or a damage found in the car's history (a VIN check,
    an auction record), with the country and an optional photo of the damage."""
    data = request.form
    af = data.get("accident_free")
    photo = None
    upload = request.files.get("photo")
    if upload and upload.filename:
        raw = upload.read(DAMAGE_PHOTO_MAX_BYTES + 1)
        if len(raw) > DAMAGE_PHOTO_MAX_BYTES:
            flash("Zdjęcie jest za duże (maks. 4 MB). Wpis nie został dodany.", "danger")
            return redirect(url_for("vehicles.vehicle_detail", vin=vin))
        try:
            photo = store_photo(raw, f"damage/{_photo_slug(vin)}_{int(time.time())}.jpg", max_width=1600, quality=80)
        except Exception:
            flash("Nie udało się odczytać zdjęcia (obsługiwane: JPG, PNG, WebP). Wpis nie został dodany.", "danger")
            return redirect(url_for("vehicles.vehicle_detail", vin=vin))
    conn = get_db()
    verification.add_condition_report(
        conn, vin,
        report_date=data.get("report_date") or None,
        mileage_km=safe_int(data.get("mileage_km")),
        accident_free=1 if af == "yes" else (0 if af == "no" else None),
        service_history=(data.get("service_history") or "").strip() or None,
        condition_score=safe_int(data.get("condition_score")),
        inspection_by=(data.get("inspection_by") or "").strip() or None,
        notes=(data.get("notes") or "").strip() or None,
        country=(data.get("country") or "").strip() or None,
        photo=photo,
    )
    conn.close()
    flash("Dodano wpis do historii auta.", "success")
    return redirect(url_for("vehicles.vehicle_detail", vin=vin) + "#history")


@bp.route("/vehicle/<path:vin>/delete_condition/<int:report_id>", methods=["POST"])
def delete_condition(vin, report_id):
    """Removes one condition report (its photo stays in storage)."""
    conn = get_db()
    conn.execute("DELETE FROM condition_reports WHERE id = ? AND vin = ?", (report_id, vin))
    conn.commit()
    conn.close()
    flash("Usunięto wpis z historii auta.", "success")
    return redirect(url_for("vehicles.vehicle_detail", vin=vin) + "#history")


def _photo_slug(vin):
    return "".join(ch for ch in vin if ch.isalnum())[:40] or "car"


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
        reg_plate = normalize_plate(reg_plate) or None
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
# DAMAGE MARK — dismiss a wrong "Uszkodzony", or bring it back
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>/damage_mark", methods=["POST"])
def set_damage_mark(vin):
    """Form field dismissed=1: the car's ads are not damaged after all (a wrong match in the ad's
    text, a seller's mistake); 0 brings the marks back. The rows stay, so a later scrape of the
    same ad does not mark it again."""
    dismissed = request.form.get("dismissed") == "1"
    conn = get_db()
    verification.set_damage_dismissed(conn, vin, dismissed)
    conn.close()
    flash("Oznaczenie „Uszkodzony” zdjęte: auto wraca do statystyk cen." if dismissed
          else "Oznaczenie „Uszkodzony” przywrócone.", "success")
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


@bp.route("/vehicle/<path:vin>/data_checked", methods=["POST"])
def set_data_checked(vin):
    """Form field checked=1: the car's plate, first registration date, origin and damage are checked
    ("Dane sprawdzone"); 0 takes the mark back."""
    conn = get_db()
    found = verification.set_data_checked(conn, vin, request.form.get("checked") == "1")
    conn.close()
    if not found:
        return "Nie znaleziono VIN-u", 404
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


# ─────────────────────────────────────────────────────────────────────────────
# WRONG MODEL — hide a car that is not the model it was filed under
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/vehicle/<path:vin>/wrong_model", methods=["POST"])
def mark_wrong_model(vin):
    """Hide the car from lists and statistics: its listings are rejected with the reason and its
    sightings excluded. Nothing is deleted, so the VIN stays known and "Przywróć" undoes it."""
    reason = " ".join(request.form.get("reason", "").split())[:200]
    if not reason:
        flash("Podaj, czym to auto jest naprawdę (np. „M8 Gran Coupé, nie M5”).", "error")
        return redirect(url_for("vehicles.vehicle_detail", vin=vin))
    conn = get_db()
    conn.execute("UPDATE pending_listings SET status = 'rejected', reviewed_at = datetime('now'), review_notes = ? "
                 "WHERE vin = ? AND status IN ('approved', 'pending')", (WRONG_MODEL_NOTE + reason, vin))
    conn.execute("UPDATE listing_observations SET excluded_reason = ? WHERE vin = ? AND excluded_reason IS NULL",
                 (WRONG_MODEL, vin))
    conn.commit()
    conn.close()
    flash("Auto ukryte: nie pojawi się na listach ani w statystykach. Nowe ogłoszenia z tym VIN-em będą odrzucane.", "success")
    return redirect(url_for("vehicles.vehicle_detail", vin=vin))


@bp.route("/vehicle/<path:vin>/restore_model", methods=["POST"])
def restore_wrong_model(vin):
    """Undo mark_wrong_model: the listings it rejected are approved again, the sightings count again."""
    conn = get_db()
    conn.execute("UPDATE pending_listings SET status = 'approved', review_notes = NULL "
                 "WHERE vin = ? AND status = 'rejected' AND review_notes LIKE ?", (vin, WRONG_MODEL_NOTE + "%"))
    conn.execute("UPDATE listing_observations SET excluded_reason = NULL WHERE vin = ? AND excluded_reason = ?",
                 (vin, WRONG_MODEL))
    conn.commit()
    conn.close()
    flash("Auto przywrócone.", "success")
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
    conn.execute("DELETE FROM favorites WHERE vin=?", (vin,))
    conn.execute("DELETE FROM vin_correction_log WHERE old_vin=? OR new_vin=?", (vin, vin))
    conn.execute("DELETE FROM vehicles WHERE vin=?", (vin,))
    conn.commit()
    conn.close()
    return redirect(url_for("vehicles.vehicles_list"))
