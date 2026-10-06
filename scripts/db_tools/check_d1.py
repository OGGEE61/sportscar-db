import os
from db import get_db

conn = get_db()

print("Alpinas in vehicles:")
alpinas = conn.execute("SELECT vin, make, model FROM vehicles WHERE make='Alpina'").fetchall()
for a in alpinas:
    print(dict(a))
    obs = conn.execute("SELECT * FROM listing_observations WHERE vin=?", (a["vin"],)).fetchall()
    print(f"  observations: {len(obs)}")

print("\nVehicles with 'missing plates' tag:")
tagged = conn.execute("SELECT v.vin, v.registration_plate, v.vin_status, t.tag FROM vehicles v JOIN tags t ON v.vin = t.vin WHERE t.tag='missing plates' LIMIT 10").fetchall()
for t in tagged:
    print(dict(t))
