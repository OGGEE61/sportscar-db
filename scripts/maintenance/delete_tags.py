import os

def run():
    from db import get_db
    conn = get_db()
    conn.execute("DELETE FROM tags WHERE tag IN ('missing plates', 'Missing plates')")
    conn.commit()
    print("Deleted tags.")

# Local SQLite
print("Local DB:")
if "DB_BACKEND" in os.environ:
    del os.environ["DB_BACKEND"]
run()

# D1
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

print("D1 DB:")
run()
