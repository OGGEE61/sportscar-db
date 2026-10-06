import os

with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from db import get_db
from app import _approve_listing
conn = get_db()

pls = conn.execute("SELECT * FROM pending_listings WHERE status='approved'").fetchall()
count = 0
for p in pls:
    obs = conn.execute("SELECT COUNT(*) as c FROM listing_observations WHERE source_listing_id=? AND source=?", (p["source_listing_id"], p["source"])).fetchone()
    if obs["c"] == 0:
        print(f"Fixing missing obs for {p['vin']} (ID: {p['id']})")
        try:
            _approve_listing(conn, dict(p))
            count += 1
        except Exception as e:
            print("Failed:", e)

print(f"Fixed {count} approved listings with 0 obs.")
