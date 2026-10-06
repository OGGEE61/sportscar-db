import os

with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from db import get_db
from app import _approve_listing, make_placeholder_vin
conn = get_db()

pending = conn.execute("SELECT * FROM pending_listings WHERE status='pending'").fetchall()
count = 0
for p in pending:
    vin = (p["vin"] or "").strip().upper()
    if not vin or len(vin) != 17:
        vin = make_placeholder_vin(p["source"] or "olx", p["source_listing_id"] or str(p["id"]))
        
    in_vehicles = conn.execute("SELECT 1 FROM vehicles WHERE vin=?", (vin,)).fetchone()
    if in_vehicles:
        try:
            _approve_listing(conn, dict(p))
            count += 1
            print(f"Fixed {vin}")
        except Exception as e:
            print(f"Failed {vin}: {e}")

print(f"Total fixed: {count}")
