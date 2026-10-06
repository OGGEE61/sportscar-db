import os
import re

# manually parse .env
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from db import get_db

conn = get_db()
print("Connected to:", os.environ.get("DB_BACKEND"))

# 1. Fix missing plates
vehicles = conn.execute("SELECT vin, registration_plate, vin_status FROM vehicles").fetchall()
updated_verified = 0
updated_unverified = 0

for v in vehicles:
    vin = v["vin"]
    plate = v["registration_plate"]
    
    if vin.startswith("UNVERIFIED"):
        if v["vin_status"] != "placeholder":
            conn.execute("UPDATE vehicles SET vin_status='placeholder' WHERE vin=?", (vin,))
        continue
        
    if plate and plate.strip():
        if v["vin_status"] != "verified":
            conn.execute("UPDATE vehicles SET vin_status='verified' WHERE vin=?", (vin,))
            updated_verified += 1
    else:
        if v["vin_status"] != "unverified":
            conn.execute("UPDATE vehicles SET vin_status='unverified' WHERE vin=?", (vin,))
            updated_unverified += 1

print(f"Verified {updated_verified} vehicles, unverified/tagged {updated_unverified} vehicles.")

# 2. Check Alpinas
alpinas = conn.execute("SELECT vin, make, model FROM vehicles WHERE make='Alpina'").fetchall()
print(f"Alpinas in DB: {len(alpinas)}")
for a in alpinas:
    obs = conn.execute("SELECT COUNT(*) as c FROM listing_observations WHERE vin=?", (a["vin"],)).fetchone()["c"]
    print(f"VIN: {a['vin']} has {obs} observations.")
