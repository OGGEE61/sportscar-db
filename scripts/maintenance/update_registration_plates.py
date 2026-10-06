import time
from db import get_db
from scrapers.base_scraper import load_cookies, refresh_session, fetch_detail

vins_to_check = [
    "JTDAF4E330A028267", "JTDAF4E330A022730", "JTDAF4E350A012541", "JTDAF4E370A028630",
    "JTDAF4E390A025468", "JTDAF4E3X0A005553", "WBA81DP0409P76461", "WBATS31080LC20XXX",
    "WBA81DP0109J85XXX", "WBS21DM0708F20224", "WBS21DM0808F22511", "WBS11DM0708E42094",
    "WBS21DM0708G30716", "WBS41DM0008G81578", "WBS21DM0408G30821", "WBS21DM0508G80675",
    "WBS21DM0608G23935", "WBS41DM0108G77278", "12345678912345678", "WBS21DM0508G79350",
    "WBS21DM0708G36953", "WBS11DM0608D99559", "WBS21DM0008G89879", "WBS41DM0X08G79403",
    "WBS21DM0508F24927", "WBS41DM0008G75344", "WBS41DM0908G84480", "WBS21DM0308G97426",
    "WBS21DM0X08F30321", "WBS41DM0308G96642", "5UXTS3C52K0Z04594", "5UXTY9C05L9B23512",
    "5UXTY9C0XM9H48750", "WUAZZZ8V6JA900269", "5UX83DP05N9K95444", "5UXTY9C02L9C73898",
    "WBSTS010009B97071", "5UX83DP03P9R72994", "5UXTY9C05M9G68756", "WUABWGFF4J1905304",
    "WBS3S7C04LAH85063", "WBS4Y9C53JAC88089", "WUAZZZ8V8LA903323", "WBS8M9C37H5G85139",
    "WBS8M9C51G5E68234", "WBS8M9C59G5D30747", "WBS8M910205K18768", "WBS8M9C37H5G85674",
    "WBS8M9C59J5K99794", "WBS3C9C57FJ276137", "WBS3C9C58FP806290", "WBS3R9C31HA014159",
    "WBS4S91020K576XXX", "WBS4S91090K576973", "WBS4Y9C59JAC88050", "WBS3R91060K320877",
    "WBS3R9C53GK336280", "WBS3U9C59FP967888", "WBS3R9C57GK337383", "WBS3U9C51GP968647",
    "WBS4Y9C55KAG67290", "5UXTS3C58KLR72686", "5YMTS0C00M9F39898", "WBS11EC0609N34506",
    "WBSTS01050LS73786", "WBA81DP0209L53801", "WBS3R9C57FK333770", "WBS8M9C59G5G41773",
    "WBS3R9C50HK709115", "WBS3R9C56GK336869", "WDD2040771F516271", "WUAZZZ8K8EA901628",
    "WUAZZZF4XJA903170", "WDD2040771F255776", "WDD2040771F416382", "WDDGF7HB1AF439823",
    "WDD2043771F820371", "WDDGJ7HB4CF797614", "WDDGJ7HB6DG054559", "WDD2040771F408260",
    "WDDGF7HB2EA957409", "WUABWGFF6LA901855", "WUAZZZ8V0KA904223", "WUAZZZ8V5KA905870",
    "WUAZZZ8V7JA909688", "WUAZZZ8V2LA900174"
]

def main():
    cookies = load_cookies()
    if cookies:
        cookies = refresh_session(cookies)
        
    db = get_db()
    
    for vin in vins_to_check:
        # First, try to find the url in listing_observations
        row = db.execute("SELECT source_url FROM listing_observations WHERE vin = ? AND source_url IS NOT NULL ORDER BY observed_at DESC LIMIT 1", (vin,)).fetchone()
        
        url = row["source_url"] if row else None
        if not url:
            row = db.execute("SELECT source_url FROM pending_listings WHERE vin = ? AND source_url IS NOT NULL ORDER BY scraped_at DESC LIMIT 1", (vin,)).fetchone()
            url = row["source_url"] if row else None
            
        if not url:
            print(f"Skipping {vin}: No URL found in DB.")
            continue
            
        if "otomoto.pl" not in url:
            print(f"Skipping {vin}: Not an otomoto URL ({url})")
            continue
            
        print(f"Fetching {url} for VIN {vin}...")
        details = fetch_detail(url, cookies)
        
        reg_plate = details.get("registration_plate")
        first_reg = details.get("first_registration_date")
        
        if reg_plate or first_reg:
            print(f"  -> Found plate: {reg_plate}, first reg: {first_reg}. Updating DB...")
            # Update vehicles
            db.execute("UPDATE vehicles SET registration_plate = COALESCE(?, registration_plate), first_registration_date = COALESCE(?, first_registration_date) WHERE vin = ?", (reg_plate, first_reg, vin))
            
            # Update listing_observations too if it has it
            db.execute("UPDATE listing_observations SET registration_plate = COALESCE(?, registration_plate) WHERE vin = ?", (reg_plate, vin))
            
            # Update pending_listings if it exists there
            db.execute("UPDATE pending_listings SET registration_plate = COALESCE(?, registration_plate), first_registration_date = COALESCE(?, first_registration_date) WHERE vin = ?", (reg_plate, first_reg, vin))
        else:
            print(f"  -> No plate found for {vin}")
            
        time.sleep(1.0) # sleep to avoid rate limiting
        
    db.commit()
    print("Done")

if __name__ == '__main__':
    main()
