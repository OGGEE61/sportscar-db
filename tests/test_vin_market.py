import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import get_db
from vininfo import Vin

conn = get_db()
rows = conn.execute("SELECT vin, make, origin_market, raw_description FROM pending_listings WHERE vin IS NOT NULL").fetchall()

print("VIN Analysis with vininfo:")
for row in rows:
    vin = row["vin"].upper()
    make = row["make"]
    market = row["origin_market"]
    
    try:
        v = Vin(vin)
        print(f"[{make}] {vin} - DESC says {market}, vininfo region: {v.region}, country: {v.country}")
    except Exception as e:
        pass
