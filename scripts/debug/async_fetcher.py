import asyncio
import sqlite3
import re
import json
from curl_cffi.requests import AsyncSession
from scrapers.base_scraper import _decrypt_vin

async def fetch_ad_details(session, url, vin):
    if not url or "otomoto.pl" not in url:
        return vin, None, None
        
    try:
        response = await session.get(url, impersonate="chrome", timeout=10)
        
        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.S)
        if not nd_m:
            return vin, None, None
            
        nd = json.loads(nd_m.group(1))
        advert = nd.get("props", {}).get("pageProps", {}).get("advert", {})
        if not advert:
            return vin, None, None
            
        params = {d["key"]: d["value"]
                  for d in advert.get("details", [])
                  if "key" in d and "value" in d}
                  
        advert_id = str(advert.get("id", ""))
        if not advert_id:
            return vin, None, None
            
        reg_plate = None
        enc_reg = params.get("registration", "")
        if enc_reg:
            reg_plate = _decrypt_vin(enc_reg, advert_id)
            
        reg_date = None
        enc_date = params.get("date_registration", "")
        if enc_date:
            reg_date = _decrypt_vin(enc_date, advert_id)
                
        return vin, reg_plate, reg_date
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return vin, None, None

async def main():
    conn = sqlite3.connect("sportscar_market.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch approved listings (vehicles) that lack registration details
    cursor.execute("""
        SELECT v.vin, lo.source_url 
        FROM vehicles v
        JOIN listing_observations lo ON v.vin = lo.vin
        WHERE lo.source_url IS NOT NULL
          AND (v.registration_plate IS NULL OR v.registration_plate = '')
    """)
    listings = cursor.fetchall()
    
    if not listings:
        print("No approved vehicles require enrichment.")
        conn.close()
        return

    print(f"Found {len(listings)} approved vehicles to enrich asynchronously.")
    
    # Process concurrently using an AsyncSession
    async with AsyncSession(max_clients=10) as session:
        tasks = []
        for row in listings:
            tasks.append(fetch_ad_details(session, row["source_url"], row["vin"]))
            
        results = await asyncio.gather(*tasks)
        
        updated = 0
        for vin, plate, date in results:
            if plate or date:
                cursor.execute("""
                    UPDATE vehicles 
                    SET registration_plate = COALESCE(?, registration_plate), 
                        first_registration_date = COALESCE(?, first_registration_date)
                    WHERE vin = ?
                """, (plate, date, vin))
                updated += 1
                print(f"Updated vehicle {vin} -> Plate: {plate} | Date: {date}")
                
        conn.commit()
        print(f"\nSuccessfully enriched {updated} vehicles with registration details.")
        
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
