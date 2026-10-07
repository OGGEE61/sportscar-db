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
    negation_patterns = [
        r'\bnie\s+(?:jest\s+|pochodzi\s+|sprowadz\w*\s+)?(?:z\s+|ze\s+)?(?:usa|stan[oó]w|ameryk\w*)\b',
        r'\b(?:bez|żadn\w+|to\s+nie)\s+(?:usa|stan[oó]w|ameryk\w*)\b',
        r'\bnie\s+(?:z\s+|pochodzi\s+z\s+)?(?:kanad\w+|japoni\w+|szwajcari\w+)\b',
    ]
    desc_clean = desc
    for pat in negation_patterns:
        desc_clean = re.sub(pat, " ", desc_clean)
        
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
    def has_keyword(words):
        pattern = r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b'
        return bool(re.search(pattern, desc_clean))

    if has_keyword(["zatoka perska", "zatoki", "dubaj", "gcc", "middle east", "uae", "zea", "emiraty"]):
        return "Zatoka Perska"
        
    if has_keyword(["usa", "stanów", "stany zjednoczone", "ameryka", "z ameryki", "us spec", "ameryki", "wersja ameryk"]):
        return "USA"
        
    if has_keyword(["kanady", "kanada", "z kanady", "kanadyjska"]):
        return "Kanada"
        
    if has_keyword(["japonii", "japonia", "jdm", "z japonii"]):
        return "Japonia"
        
    if has_keyword(["szwajcarii", "szwajcaria", "ze szwajcarii"]):
        return "Szwajcaria"
        
    if has_keyword(["salon polska", "salon pl", "krajowy", "krajowa", "salonowy", "polska"]):
        if has_keyword(["salon polska", "krajowy", "salon pl"]):
            return "Polska"
            
    # ---------------------------------------------------------
    # STAGE 4: VIN Fallbacks (If description didn't clarify)
    # ---------------------------------------------------------
    if vin:
        if vin.startswith(("WAU", "TRU", "WP0", "WP1", "WVW", "WPO")):
            if "ZZZ" not in vin:
                return "USA/Kanada"
                
    return None
