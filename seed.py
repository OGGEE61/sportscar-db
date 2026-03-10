"""
seed.py — Demo data showing the observation-based model.
Shows:
  - Same ad observed across multiple weeks (3 rows for one ad)
  - Price drop between observations
  - One listing with a placeholder VIN (source had no VIN)
  - VIN correction log entry
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, init_db, make_placeholder_vin
from datetime import datetime, timedelta

def ts(days_ago: int, hour: int = 10) -> str:
    d = datetime.utcnow() - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

def seed():
    init_db()
    conn = get_conn()

    # ── Vehicles ──────────────────────────────────────────────────────────────
    vehicles = [
        ("WP0ZZZ99ZTS392124", "Porsche", "911",          "Carrera 4S",    2020, "Coupe",       2981, 6, 450, "AWD", "PDK",           "GT Silver Metallic",  "Black leather",    "verified",  "manual"),
        ("WBSKG9C54BE370512", "BMW",     "M3",           "Competition",   2021, "Sedan",       2993, 6, 510, "RWD", "Automatic",     "Frozen Portimao Blue","Full Merino",      "unverified","manual"),
        ("ZAM45KLA5J0281745", "Maserati","GranTurismo",  "MC Stradale",   2018, "Coupe",       4691, 8, 460, "RWD", "Automatic",     "Rosso Trionfale",     "Nero Alcantara",   "verified",  "manual"),
        ("SAJWA2BZ4EMR12349", "Jaguar",  "F-TYPE",       "R AWD",         2019, "Coupe",       5000, 8, 550, "AWD", "Automatic",     "Santorini Black",     "Red leather",      "unverified","manual"),
        ("WDDGJ4HB1EG123456", "Mercedes-Benz","AMG GT",  "S",             2021, "Coupe",       3982, 8, 585, "RWD", "AMG Speedshift","Selenite Grey",       "Nappa Black/Red",  "verified",  "manual"),
    ]
    for v in vehicles:
        conn.execute("""
            INSERT OR IGNORE INTO vehicles
              (vin,make,model,variant,year,body_type,engine_cc,engine_cyl,power_hp,
               drivetrain,transmission,color_ext,color_int,vin_status,source_method)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, v)

    # ── Placeholder VIN (OLX listing, no VIN in ad) ───────────────────────────
    placeholder_vin = make_placeholder_vin("olx", "99887766")
    conn.execute("""
        INSERT OR IGNORE INTO vehicles
          (vin,make,model,variant,year,body_type,power_hp,drivetrain,
           vin_status,source_method)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (placeholder_vin, "Ferrari", "488", "GTB", 2017, "Coupe",
          670, "RWD", "placeholder", "scraper-olx"))

    # ── Observations ──────────────────────────────────────────────────────────
    # Porsche 911: same OtoMoto ad observed 3 times over 3 weeks — price drops
    porsche_obs = [
        ("WP0ZZZ99ZTS392124", "otomoto", "OT-48291001", "https://otomoto.pl/48291001",
         "Porsche 911 Carrera 4S PDK, bezwypadkowy",
         389000, None, 22000, "Warszawa", "Mazowieckie", "private", None,
         ts(21), ts(21), ts(21), None, "scraper-otomoto", None),
        ("WP0ZZZ99ZTS392124", "otomoto", "OT-48291001", "https://otomoto.pl/48291001",
         "Porsche 911 Carrera 4S PDK, bezwypadkowy",
         375000, None, 22000, "Warszawa", "Mazowieckie", "private", None,
         ts(21), ts(14), ts(14), None, "scraper-otomoto", "Price dropped 14k"),
        ("WP0ZZZ99ZTS392124", "otomoto", "OT-48291001", "https://otomoto.pl/48291001",
         "Porsche 911 Carrera 4S PDK, bezwypadkowy",
         365000, None, 22000, "Warszawa", "Mazowieckie", "private", None,
         ts(21), ts(7),  ts(7),  None, "scraper-otomoto", "Price dropped another 10k"),
    ]
    # BMW M3: two observations, then removed
    bmw_obs = [
        ("WBSKG9C54BE370512", "otomoto", "OT-56103882", "https://otomoto.pl/56103882",
         "BMW M3 Competition, przebieg 8500km",
         295000, None, 8500, "Kraków", "Małopolskie", "dealer", "Premium Auto",
         ts(30), ts(30), ts(30), None, "scraper-otomoto", None),
        ("WBSKG9C54BE370512", "otomoto", "OT-56103882", "https://otomoto.pl/56103882",
         "BMW M3 Competition, przebieg 8500km",
         295000, None, 8500, "Kraków", "Małopolskie", "dealer", "Premium Auto",
         ts(30), ts(20), ts(20), ts(20), "scraper-otomoto", "Ad removed — likely sold"),
    ]
    # Maserati: manual entry, no source_listing_id
    maserati_obs = [
        ("ZAM45KLA5J0281745", "manual", None, None,
         None, 310000, 72000, 61000, "Wrocław", "Dolnośląskie", "private", None,
         ts(15), ts(15), ts(15), None, "manual", "Seen on Facebook Marketplace"),
    ]
    # Jaguar: OLX
    jaguar_obs = [
        ("SAJWA2BZ4EMR12349", "olx", "OLX-77234411", "https://olx.pl/77234411",
         "Jaguar F-Type R AWD Coupe",
         220000, 51000, 44000, "Gdańsk", "Pomorskie", "private", None,
         ts(10), ts(10), ts(10), None, "scraper-olx", None),
    ]
    # AMG GT: dealer, manual entry
    amg_obs = [
        ("WDDGJ4HB1EG123456", "dealer", None, None,
         None, 590000, None, 5200, "Poznań", "Wielkopolskie", "dealer", "Auto Prestige Poznań",
         ts(5), ts(5), ts(5), None, "manual", None),
    ]
    # Placeholder Ferrari: two observations
    ferrari_obs = [
        (placeholder_vin, "olx", "99887766", "https://olx.pl/99887766",
         "Ferrari 488 GTB, serwis ASO",
         1200000, None, 8800, "Warszawa", "Mazowieckie", "private", None,
         ts(18), ts(18), ts(18), None, "scraper-olx", "VIN not shown in listing"),
        (placeholder_vin, "olx", "99887766", "https://olx.pl/99887766",
         "Ferrari 488 GTB, serwis ASO",
         1150000, None, 8800, "Warszawa", "Mazowieckie", "private", None,
         ts(18), ts(11), ts(11), None, "scraper-olx", "Price reduced"),
    ]

    for obs_list in [porsche_obs, bmw_obs, maserati_obs, jaguar_obs, amg_obs, ferrari_obs]:
        for o in obs_list:
            conn.execute("""
                INSERT INTO listing_observations
                  (vin,source,source_listing_id,source_url,title,price_pln,price_eur,
                   mileage_km,location_city,location_region,seller_type,seller_name,
                   first_seen_at,observed_at,last_seen_at,removed_at,source_method,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, o)

    # ── Tags ──────────────────────────────────────────────────────────────────
    tag_data = [
        ("WP0ZZZ99ZTS392124", ["rare","low-mileage","collector"],         "manual"),
        ("WBSKG9C54BE370512", ["limited-color","likely-sold"],            "manual"),
        ("ZAM45KLA5J0281745", ["collector","italian","facebook"],         "manual"),
        ("SAJWA2BZ4EMR12349", ["bargain"],                                "manual"),
        ("WDDGJ4HB1EG123456", ["low-mileage","dealer"],                   "manual"),
        (placeholder_vin,      ["placeholder","verify-vin","exotic"],      "scraper-olx"),
    ]
    for vin, taglist, method in tag_data:
        for tag in taglist:
            conn.execute(
                "INSERT OR IGNORE INTO tags(vin,tag,source_method) VALUES(?,?,?)",
                (vin, tag, method))

    # ── Condition reports ─────────────────────────────────────────────────────
    conditions = [
        ("WP0ZZZ99ZTS392124", "2025-01-15", 22000, 1, "full",    9, "ASO Porsche Warszawa",   "manual"),
        ("WBSKG9C54BE370512", "2025-01-25", 8500,  1, "full",    9, "BMW Dealer Kraków",      "manual"),
        ("ZAM45KLA5J0281745", "2025-02-01", 61000, 1, "partial", 7, "Prywatny mechanik",      "manual"),
        ("SAJWA2BZ4EMR12349", "2025-01-20", 44000, 1, "full",    8, None,                     "manual"),
        ("WDDGJ4HB1EG123456", "2025-02-20", 5200,  1, "full",   10, "Mercedes-Benz ASO Poznań","manual"),
    ]
    for vin, rdate, km, af, svc, score, insp, method in conditions:
        conn.execute("""
            INSERT INTO condition_reports
              (vin,report_date,mileage_km,accident_free,service_history,
               condition_score,inspection_by,source_method)
            VALUES (?,?,?,?,?,?,?,?)
        """, (vin, rdate, km, af, svc, score, insp, method))

    conn.commit()
    conn.close()
    print("OK  Seed complete.")
    print(f"    Placeholder VIN created: {placeholder_vin}")
    print("    Resolve it later via UI: /vehicle/" + placeholder_vin)

if __name__ == "__main__":
    seed()
