import sqlite3
import time
from app import CITY_TO_REGION, _enrich_location_with_nominatim

def update_regions():
    conn = sqlite3.connect('sportscar_market.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    def process_table(table_name):
        print(f"--- Processing {table_name} ---")
        cursor.execute(f'''
            SELECT id, location_city 
            FROM {table_name} 
            WHERE location_city IS NOT NULL AND location_city != '' 
              AND (location_region IS NULL OR length(location_region) != 5)
        ''')
        rows = cursor.fetchall()
        
        updated = 0
        for row in rows:
            record_id = row['id']
            city = row['location_city'].strip()
            
            region = CITY_TO_REGION.get(city)
            if not region or len(region) != 5:
                # Use Nominatim API fallback
                region = _enrich_location_with_nominatim(city)
                if region:
                    time.sleep(1.1)  # rate limit Nominatim
                
            if region and len(region) == 5:
                conn.execute(f'UPDATE {table_name} SET location_region = ? WHERE id = ?', (region, record_id))
                updated += 1
                print(f"Updated {city} -> {region}")
                conn.commit()
                
        print(f"Finished {table_name}: updated {updated} records.\n")

    process_table('listing_observations')
    process_table('pending_listings')
    
    conn.close()

if __name__ == '__main__':
    update_regions()
