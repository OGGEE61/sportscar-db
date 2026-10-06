import os
import traceback

with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from db import get_db
from app import _approve_listing

conn = get_db()
# Get one pending Alpina
listing = conn.execute("SELECT * FROM pending_listings WHERE status='pending' AND make='Alpina' LIMIT 1").fetchone()
if listing:
    print(f"Testing approve for Alpina ID {listing['id']} (VIN: {listing['vin']})")
    try:
        vin = _approve_listing(conn, dict(listing))
        print("Success! VIN:", vin)
    except Exception as e:
        print("Error during approve:")
        traceback.print_exc()
else:
    print("No pending Alpina found.")
