import re
from db import get_db

def is_valid_plate(plate):
    if not plate or not isinstance(plate, str):
        return False
        
    cleaned_plate = re.sub(r"[\s\-\.]", "", plate).upper()
    
    # Polish plates have between 4 and 8 characters max
    if len(cleaned_plate) < 4 or len(cleaned_plate) > 8:
        return False
        
    if not re.fullmatch(r"[A-Z0-9]+", cleaned_plate):
        return False

    # Must contain at least one letter and at least one digit
    if not (re.search(r"[A-Z]", cleaned_plate) and re.search(r"[0-9]", cleaned_plate)):
        return False
        
    blacklist = ["SALONPL", "BRAK", "AUTO", "TEST", "NIE", "XXX", "ALEJAAUT", "STAN", "NOWY", "DEALER", "BEZWYP"]
    if any(bad in cleaned_plate for bad in blacklist):
        return False
        
    if len(set(cleaned_plate)) <= 1:
        return False
        
    return True

def main():
    db = get_db()
    
    tables = ["vehicles", "listing_observations", "pending_listings"]
    
    for table in tables:
        # Fetch all non-null plates
        rows = db.execute(f"SELECT id, registration_plate FROM {table} WHERE registration_plate IS NOT NULL" if table != "vehicles" else f"SELECT vin as id, registration_plate FROM {table} WHERE registration_plate IS NOT NULL").fetchall()
        
        updates = []
        for row in rows:
            plate = row["registration_plate"]
            if not is_valid_plate(plate):
                updates.append(row["id"])
            else:
                # Optional: normalize it to uppercase
                pass
                
        if updates:
            print(f"Cleaning up {len(updates)} invalid plates in {table}...")
            # Because of D1 limits, process in chunks
            chunk_size = 50
            for i in range(0, len(updates), chunk_size):
                chunk = updates[i:i+chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                if table == "vehicles":
                    db.execute(f"UPDATE {table} SET registration_plate = NULL WHERE vin IN ({placeholders})", chunk)
                else:
                    db.execute(f"UPDATE {table} SET registration_plate = NULL WHERE id IN ({placeholders})", chunk)
                    
    db.commit()
    print("Cleanup done.")

if __name__ == '__main__':
    main()
