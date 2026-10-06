import re

def resolve_market(vin: str, description: str, make: str = None) -> str:
    """
    Multi-stage market resolution system.
    Determines the origin market of a vehicle based on VIN structure and description heuristics.
    """
    desc = (description or "").lower()
    vin = (vin or "").strip().upper()
    
    # ---------------------------------------------------------
    # STAGE 1: Sanitize description to prevent false positives
    # ---------------------------------------------------------
    negations = [
        "nie usa", "bez usa", "nie z usa", "nie ze stanow", 
        "nie stany", "nie z ameryki", "to nie usa", "nie ameryka"
    ]
    desc_clean = desc
    for n in negations:
        desc_clean = desc_clean.replace(n, "")
        
    # ---------------------------------------------------------
    # STAGE 2: Strong VIN rules (Definitive)
    # ---------------------------------------------------------
    if vin:
        # 1. JDM short chassis codes (e.g., S2000 AP1-130..., Skyline BNR34-...)
        # Japanese domestic market cars don't use standard 17-char VINs
        if len(vin) >= 9 and len(vin) < 17 and make in ["Honda", "Toyota", "Nissan", "Mazda", "Subaru", "Mitsubishi"]:
            return "Japonia"
            
        # 2. VAG & Porsche ZZZ rule
        # European VAG/Porsche cars use ZZZ as filler in positions 7-9. 
        # North American cars use these positions for real data (check digit, etc.)
        if vin.startswith(("WAU", "TRU", "WP0", "WP1", "WVW", "WPO")):
            if "ZZZ" in vin:
                return "Europa"
                
    # ---------------------------------------------------------
    # STAGE 3: Description Keyword Matching
    # ---------------------------------------------------------
    if any(w in desc_clean for w in ["zatoka perska", "zatoki", "dubaj", "gcc", "middle east", "uae", "zje", "emiraty"]):
        return "Zatoka Perska"
        
    if any(w in desc_clean for w in ["usa", "stanów", "stany zjednoczone", "ameryka", "z ameryki", "us spec", "ameryki", "wersja ameryk"]):
        return "USA"
        
    if any(w in desc_clean for w in ["kanady", "kanada", "z kanady", "kanadyjska"]):
        return "Kanada"
        
    if any(w in desc_clean for w in ["japonii", "japonia", "jdm", "z japonii"]):
        return "Japonia"
        
    if any(w in desc_clean for w in ["szwajcarii", "szwajcaria", "ze szwajcarii"]):
        return "Szwajcaria"
        
    if any(w in desc_clean for w in ["salon polska", "salon pl", "krajowy", "krajowa", "salonowy", "polska"]):
        # A bit risky to just map "polska" -> Europa, but "salon polska" is very strong
        if "salon polska" in desc_clean or "krajowy" in desc_clean or "salon pl" in desc_clean:
            return "Europa"
            
    # ---------------------------------------------------------
    # STAGE 4: VIN Fallbacks (If description didn't clarify)
    # ---------------------------------------------------------
    if vin:
        if vin.startswith(("WAU", "TRU", "WP0", "WP1", "WVW", "WPO")):
            if "ZZZ" not in vin:
                return "USA/Kanada"
                
    return None
