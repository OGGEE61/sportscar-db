import os

with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from db import get_db
conn = get_db()

cols_to_add = [
    "registration_plate TEXT",
    "seller_name TEXT",
    "location_region TEXT"
]

for col in cols_to_add:
    try:
        conn.execute(f"ALTER TABLE listing_observations ADD COLUMN {col}")
        print(f"Success adding {col}")
    except Exception as e:
        print(f"Failed to add {col}: {e}")
