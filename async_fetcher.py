import asyncio
import sqlite3
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

async def fetch_ad_details(session, url, listing_id):
    if not url or "otomoto.pl" not in url:
        return listing_id, None, None
        
    try:
        response = await session.get(url, impersonate="chrome", timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        reg_plate, reg_date = None, None
        
        for el in soup.find_all(["p", "span", "div"]):
            txt = el.get_text(strip=True)
            if txt == "Numer rejestracyjny pojazdu":
                nxt = el.find_next_sibling()
                if nxt: reg_plate = nxt.get_text(strip=True)
            elif txt == "Pierwsza rejestracja":
                nxt = el.find_next_sibling()
                if nxt: reg_date = nxt.get_text(strip=True)
                
        return listing_id, reg_plate, reg_date
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return listing_id, None, None

async def main():
    conn = sqlite3.connect("sportscar_market.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch pending listings that lack registration details
    cursor.execute("""
        SELECT id, source_url 
        FROM pending_listings 
        WHERE status = 'pending' 
          AND (registration_plate IS NULL OR registration_plate = '')
    """)
    listings = cursor.fetchall()
    
    if not listings:
        print("No pending listings require enrichment.")
        conn.close()
        return

    print(f"Found {len(listings)} listings to enrich asynchronously.")
    
    # Process concurrently using an AsyncSession
    async with AsyncSession(max_clients=10) as session:
        tasks = []
        for row in listings:
            tasks.append(fetch_ad_details(session, row["source_url"], row["id"]))
            
        results = await asyncio.gather(*tasks)
        
        updated = 0
        for listing_id, plate, date in results:
            if plate or date:
                cursor.execute("""
                    UPDATE pending_listings 
                    SET registration_plate = COALESCE(?, registration_plate), 
                        first_registration_date = COALESCE(?, first_registration_date)
                    WHERE id = ?
                """, (plate, date, listing_id))
                updated += 1
                print(f"Updated listing {listing_id} -> Plate: {plate} | Date: {date}")
                
        conn.commit()
        print(f"\nSuccessfully enriched {updated} listings with registration details.")
        
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
