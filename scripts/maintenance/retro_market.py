import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import get_db, init_db

from scrapers.market_resolver import resolve_market

def run_retroactive_market():
    # Make sure migrations are run (this will add the origin_market column)
    init_db()

    conn = get_db()
    
    print("Fetching pending listings...")
    rows = conn.execute("SELECT id, source_listing_id, raw_description, vin, status, make FROM pending_listings WHERE raw_description IS NOT NULL").fetchall()
    print(f"Found {len(rows)} listings with descriptions.")
    
    updated_pending = 0
    updated_vehicles = 0

    for row in rows:
        origin_market = resolve_market(row["vin"], row["raw_description"], make=row["make"])
            
        # Update pending_listings
        conn.execute("UPDATE pending_listings SET origin_market = ? WHERE id = ?", (origin_market, row["id"]))
        if origin_market:
            updated_pending += 1
        
        # If approved, also update vehicles table
        if row["status"] == "approved" and row["vin"]:
            conn.execute("UPDATE vehicles SET origin_market = ? WHERE vin = ?", (origin_market, row["vin"]))
            if origin_market:
                updated_vehicles += 1
                
    if hasattr(conn, "commit"):
        conn.commit()
        
    print(f"Done. Updated {updated_pending} pending listings and {updated_vehicles} vehicles.")

if __name__ == "__main__":
    run_retroactive_market()
