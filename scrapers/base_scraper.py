"""
Shared scraping engine for OLX / Otomoto listings.
Each model scraper imports `run` from here and passes a ScraperConfig.

Cookie auth (otomoto VIN decryption)
-------------------------------------
1. Log into otomoto.pl in Chrome
2. Install the "Cookie-Editor" browser extension
3. Click Export -> "Export as JSON" -> save to  scrapers/otomoto_cookies.json
4. The scraper loads that file automatically — VINs will be decrypted server-side.

Why curl_cffi?
--------------
otomoto uses DataDome bot-detection which checks the TLS fingerprint of the
client.  The standard `requests` library uses Python's OpenSSL and produces a
fingerprint that DataDome blocks.  curl_cffi wraps libcurl compiled with
Chrome's BoringSSL, so the fingerprint is indistinguishable from a real browser.
"""

import os
import re
import json
import time
import random
import hashlib
import base64
from dataclasses import dataclass, field
from typing import Optional

from curl_cffi import requests
from bs4 import BeautifulSoup

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

API_BASE     = os.environ.get("BASE_URL") or os.environ.get("VERCEL_URL") or "http://127.0.0.1:5555"
API_URL      = f"{API_BASE}/api/ingest_pending"
API_TOKEN    = os.environ.get("API_TOKEN")
API_HEADERS  = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
BROWSER_UA   = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)
HEADERS      = {
    "User-Agent": BROWSER_UA,
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}
VIN_RE       = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "otomoto_cookies.json")


def is_plausible_vin(vin: str) -> bool:
    """Return True if vin looks like a real VIN.

    We can't use the ISO check digit for European cars (only NA-market VINs
    have a mandated check digit at position 9), so we use softer heuristics:
      - 17 chars, valid charset
      - at least 5 distinct characters  (rejects all-same-digit fakes)
      - no single character appears 7+ times (rejects heavily-repeated fakes)
    """
    if not vin or len(vin) != 17:
        return False
    vin = vin.upper()
    if not VIN_RE.fullmatch(vin):
        return False
    if len(set(vin)) < 5:
        return False
    if max(vin.count(c) for c in set(vin)) >= 7:
        return False
    return True


# ── config ────────────────────────────────────────────────────────────────────

@dataclass
class ScraperConfig:
    make:    str
    model:   str
    variant: Optional[str] = None       # e.g. "8V", "B8", "W204"

    # "otomoto" or "olx"
    source: str = "otomoto"

    # List-page URL template(s) — must contain {page}
    list_url: str | list[str] = ""

    # Keyword that must appear in the card title (case-insensitive).
    # Use when no model-specific URL filter exists (e.g. Mercedes C63).
    title_must_contain: Optional[str] = None
    min_year: Optional[int] = None
    max_year: Optional[int] = None

    pages:        int   = 5
    detail_delay: float = 1.0

    # Known model specs — auto-filled when the scraped page doesn't return a value.
    # e.g. RS3 8V is always 400 HP petrol AWD — no need to parse it per listing.
    defaults: dict = field(default_factory=dict)


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    """Replace non-ASCII chars so the terminal never crashes on cp1250."""
    return text.encode("ascii", errors="replace").decode("ascii")


def parse_price(text: str) -> Optional[int]:
    # Polish format: "238 435,50 zł" — space=thousands sep, comma=decimal sep
    text = re.sub(r"[^\d ,.]", "", text).strip()  # keep digits, space, comma, dot
    text = text.replace(" ", "").replace(",", ".")  # "238435.50"
    try:
        return round(float(text))
    except ValueError:
        return None


def load_cookies() -> dict:
    """Load cookies from otomoto_cookies.json.

    Accepts two formats:
      - Cookie-Editor JSON array: [{name, value, ...}, ...]
      - Simple flat dict:         {name: value, ...}
    """
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                return {c["name"]: c["value"] for c in data
                        if "name" in c and "value" in c}
            return data
        except Exception:
            pass
    return {}


def refresh_session(cookies: dict) -> dict:
    """Try to get a fresh id_token using the Cognito refresh_token.

    The id_token expires after 15 minutes. The refresh_token lasts ~30 days.
    When the id_token is stale otomoto's server won't decrypt VINs even though
    the session cookie is still present.

    Returns an updated cookies dict with a fresh id_token, or the original
    dict unchanged if refresh fails (scraper will still work, just no VINs).
    """
    refresh_token = cookies.get("refresh_token")
    client_id     = cookies.get("client_id")
    if not refresh_token or not client_id:
        return cookies

    # Cognito user pool is embedded in the id_token issuer claim
    id_token_raw = cookies.get("id_token", "")
    try:
        # Decode the middle part of the JWT (no signature verification needed)
        import base64
        payload_b64 = id_token_raw.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)   # pad
        payload     = json.loads(base64.b64decode(payload_b64))
        issuer      = payload.get("iss", "")            # e.g. https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_bigbq34vj
        pool_domain = issuer.rstrip("/")
    except Exception:
        return cookies

    # Cognito region + pool are in the issuer URL:
    # https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_bigbq34vj
    # The Identity Provider API endpoint is just the base domain.
    region   = pool_domain.split("cognito-idp.")[1].split(".amazonaws")[0]
    idp_url  = f"https://cognito-idp.{region}.amazonaws.com/"
    try:
        r = requests.post(
            idp_url,
            json={
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "ClientId": client_id,
                "AuthParameters": {"REFRESH_TOKEN": refresh_token},
            },
            headers={
                "Content-Type":  "application/x-amz-json-1.1",
                "X-Amz-Target":  "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            timeout=10,
            impersonate="chrome",
        )
        if r.status_code != 200:
            print(f"[auth] Token refresh failed: HTTP {r.status_code} -- {r.text[:120]}")
            return cookies
        tokens       = r.json().get("AuthenticationResult", {})
        new_id_token = tokens.get("IdToken")
        if not new_id_token:
            print("[auth] Token refresh: no IdToken in response")
            return cookies
        updated = dict(cookies)
        updated["id_token"] = new_id_token
        print("[auth] id_token refreshed -- VINs should now decrypt.")
        return updated
    except Exception as e:
        print(f"[auth] Token refresh error: {_safe(str(e))}")
        return cookies


def _decrypt_vin(encrypted: str, advert_id: str) -> Optional[str]:
    """Decrypt an otomoto encrypted VIN using the advert's numeric ID as key material.

    Algorithm (reverse-engineered from the otomoto JS bundle):
      password = SHA-256(advert_id)[:16 bytes] as lowercase hex string
      key      = PBKDF2-HMAC-SHA256(password, salt, iterations=10, length=32)
      vin      = AES-256-GCM-decrypt(ciphertext, iv)

    The encrypted value format is: base64(cipher).version.base64(iv)
    """
    if not _CRYPTO_OK or not encrypted or "." not in encrypted:
        return None
    try:
        parts    = encrypted.split(".")
        data     = base64.b64decode(parts[0])
        version  = parts[1]
        iv       = base64.b64decode(parts[2])
        password = hashlib.sha256(str(advert_id).encode()).digest()[:16].hex().encode()
        salt     = b"d2905222-d0c5-4ec5-bfcf-e9c29041de3c"
        iters    = 10 if (version and version != "0") else 10000
        key      = hashlib.pbkdf2_hmac("sha256", password, salt, iters, dklen=32)
        return _AESGCM(key).decrypt(iv, data, None).decode()
    except Exception:
        return None


def check_session(cookies: dict) -> bool:
    """Returns True if the cookies represent an authenticated otomoto session."""
    try:
        r = requests.get(
            "https://www.otomoto.pl/api/auth/session",
            headers=HEADERS, cookies=cookies,
            timeout=10, impersonate="chrome",
        )
        data = r.json()
        user = data.get("user") or data.get("data", {}).get("user")
        if user:
            name = user.get("name") or user.get("email") or "?"
            print(f"[auth] Logged in as: {_safe(str(name))}")
            return True
        print("[auth] Session check: NOT logged in (VINs will stay encrypted)")
        return False
    except Exception as e:
        print(f"[auth] Session check failed: {_safe(str(e))}")
        return False


def reveal_vin(ad_id: str, cookies: dict) -> Optional[str]:
    """Try to fetch the decrypted VIN via otomoto's GraphQL API.

    When a logged-in user clicks 'Show VIN', the browser sends this mutation.
    Returns the 17-char VIN string or None.
    """
    try:
        r = requests.post(
            "https://www.otomoto.pl/graphql",
            json={
                "operationName": "RevealAdVin",
                "query": """
                    mutation RevealAdVin($id: ID!) {
                        revealAdVin(id: $id) {
                            vin
                        }
                    }
                """,
                "variables": {"id": str(ad_id)},
            },
            headers={**HEADERS, "Content-Type": "application/json"},
            cookies=cookies,
            timeout=10,
            impersonate="chrome",
        )
        if r.status_code != 200:
            return None
        data  = r.json()
        vin   = (data.get("data") or {}).get("revealAdVin", {}) or {}
        value = vin.get("vin") or vin.get("value")
        if value and len(value) == 17 and VIN_RE.fullmatch(value):
            return value
    except Exception:
        pass
    return None


def extract_description(nd: dict) -> str:
    """Walk __NEXT_DATA__ to find the longest 'description' string (the ad body)."""
    best = ""

    def walk(obj, depth=0):
        nonlocal best
        if depth > 10:
            return
        if isinstance(obj, dict):
            v = obj.get("description")
            if isinstance(v, str) and len(v) > len(best):
                best = v
            for child in obj.values():
                walk(child, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)

    walk(nd)
    return best


# ── detail page ───────────────────────────────────────────────────────────────

def fetch_detail(url: str, cookies: dict = None) -> dict:
    """Fetch an otomoto listing detail page and extract structured data.

    Data lives in __NEXT_DATA__ -> props -> pageProps -> advert:
      advert.details          : [{key, value}, ...]  — year, mileage, power, vin…
      advert.description      : full ad text (plain-text VIN search)
      advert.images.photos[0] : first photo URL (the "id" field IS the URL)
      advert.price.value      : price string ("149900")
    """
    try:
        r = requests.get(
            url, headers=HEADERS, cookies=cookies or {},
            timeout=15, impersonate="chrome"
        )

        if r.status_code != 200:
            print(f"    [detail] HTTP {r.status_code}")
            return {}

        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not nd_m:
            return {}

        nd     = json.loads(nd_m.group(1))
        advert = nd.get("props", {}).get("pageProps", {}).get("advert", {})
        if not advert:
            return {}

        # Flat params dict from the details list (Polish display values + encrypted fields)
        params = {d["key"]: d["value"]
                  for d in advert.get("details", [])
                  if "key" in d and "value" in d}

        # ── parametersDict: Otomoto provides clean English/numeric values here ─────
        pd = advert.get("parametersDict") or {}
        def _pd_val(key):
            """Get the first .value from parametersDict[key].values, or None."""
            entry = pd.get(key) or {}
            vals  = entry.get("values") or []
            return vals[0].get("value") if vals else None

        year         = int(params["year"])                               if "year"         in params else None
        mileage_km   = int(_pd_val("mileage"))  if _pd_val("mileage")  else \
                       int(re.sub(r"[^\d]", "", params["mileage"])) if params.get("mileage") else None
        power_hp     = int(_pd_val("engine_power")) if _pd_val("engine_power") else \
                       int(re.sub(r"[^\d]", "", params["engine_power"])) if params.get("engine_power") else None

        # engine_cc: parametersDict gives clean integer (e.g. '2979'), fallback strips 'cm3' from details
        _ec_pd       = _pd_val("engine_capacity")
        if _ec_pd and str(_ec_pd).isdigit():
            engine_cc = int(_ec_pd)
        elif params.get("engine_capacity"):
            _ec_raw   = re.sub(r"\s*cm3\s*$", "", params["engine_capacity"], flags=re.I)
            engine_cc = int(re.sub(r"[^\d]", "", _ec_raw)) if _ec_raw else None
        else:
            engine_cc = None

        # fuel_type: parametersDict gives English value (e.g. 'petrol', 'diesel', 'electric', 'hybrid')
        _ft          = _pd_val("fuel_type") or params.get("fuel_type", "")
        _ft_l        = str(_ft).lower()
        if   "petrol"   in _ft_l or "benzyn" in _ft_l:    fuel_type = "petrol"
        elif "diesel"   in _ft_l:                          fuel_type = "diesel"
        elif "electric" in _ft_l or "elektr" in _ft_l:    fuel_type = "electric"
        elif "hybrid"   in _ft_l or "hybr"   in _ft_l:    fuel_type = "hybrid"
        else:                                               fuel_type = _ft or None

        color_ext    = params.get("color")
        _dc          = _pd_val("door_count") or params.get("doors_count")
        doors        = int(re.sub(r"[^\d]", "", str(_dc))) if _dc else None

        # gearbox: parametersDict gives English 'automatic' / 'manual' — use directly
        _gb_pd       = _pd_val("gearbox") or ""
        _gb_raw      = params.get("gearbox", "")
        _gb_l        = (_gb_pd or _gb_raw).lower()
        if   "automat" in _gb_l:                                                   transmission = "automatic"
        elif "manual"  in _gb_l or "manualna" in _gb_l:                           transmission = "manual"
        elif any(x in _gb_l for x in ["semi", "p\u00f3\u0142auto", "sekwency",
                                       "dsg", "dkg", "pdc", "s-tronic",
                                       "tiptronic"]):
            transmission = "semi-auto"
        else:
            transmission = (_gb_pd or _gb_raw) or None

        # body_type: parametersDict gives English slug ('coupe', 'sedan', 'suv', 'estate' …)
        _bt_pd       = _pd_val("body_type") or ""
        _bt_raw      = params.get("body_type", "")
        _bt_l        = (_bt_pd or _bt_raw).lower()
        if   "coupe"     in _bt_l or "coup\u00e9" in _bt_l:           body_type = "Coupe"
        elif "sedan"     in _bt_l or "saloon" in _bt_l \
             or "limuzyna" in _bt_l:                                   body_type = "Sedan"
        elif "estate"    in _bt_l or "kombi"  in _bt_l \
             or "wagon"   in _bt_l:                                    body_type = "Kombi"
        elif "cabrio"    in _bt_l or "kabriolet" in _bt_l \
             or "convertible" in _bt_l:                                body_type = "Kabriolet"
        elif "hatchback" in _bt_l:                                     body_type = "Hatchback"
        elif "suv"       in _bt_l or "off-road" in _bt_l:             body_type = "SUV"
        elif _bt_pd or _bt_raw:
            body_type = (_bt_pd or _bt_raw).capitalize()
        else:
            body_type = None

        # drivetrain: parametersDict gives English slug ('rear-wheel', 'front-wheel', 'all-wheel')
        _dr_pd       = _pd_val("transmission") or ""
        _dr_raw      = params.get("transmission") or params.get("drive") or ""
        _dr_l        = (_dr_pd or _dr_raw).lower()
        if   any(x in _dr_l for x in ["all", "four", "4x4", "awd", "quattro",
                                        "4matic", "cztery", "sta\u0142y", "4wd"]): drivetrain = "AWD"
        elif any(x in _dr_l for x in ["rear", "tyl", "rwd"]):                     drivetrain = "RWD"
        elif any(x in _dr_l for x in ["front", "prz\u00f3d", "przed", "fwd"]):   drivetrain = "FWD"
        else:                                                                       drivetrain = None

        # Description text
        description_text = advert.get("description", "")

        # VIN — three tiers (best to worst):
        # 1. Client-side AES-GCM decrypt using advert.id (no login needed)
        # 2. Plain 17-char pattern typed by seller in the description text
        # 3. has_vin flag — confirms VIN exists but we couldn't extract it
        vin_found      = None
        vin_confidence = "none"
        advert_id      = advert.get("id", "")
        has_vin        = bool((pd).get("has_vin"))

        # Tier 1: decrypt the encrypted value in params["vin"]
        enc_vin = params.get("vin", "")
        if enc_vin and advert_id:
            plain = _decrypt_vin(enc_vin, advert_id)
            if plain and is_plausible_vin(plain):
                vin_found      = plain
                vin_confidence = "found_in_schema"

        # Tier 2: seller typed VIN in description text
        if not vin_found:
            for candidate in VIN_RE.findall(description_text):
                if not re.fullmatch(r"[0-9A-F]{17}", candidate):
                    vin_found      = candidate
                    vin_confidence = "found_in_description"
                    break

        # Tier 3: flag only
        if not vin_found and has_vin:
            vin_confidence = "found_in_schema"

        # Registration plate — encrypted with same AES-GCM algorithm as VIN
        registration_plate = None
        enc_reg = params.get("registration", "")
        if enc_reg and advert_id:
            registration_plate = _decrypt_vin(enc_reg, advert_id)  # same decrypt fn

        # First registration date — encrypted the same way
        first_registration_date = None
        enc_date = params.get("date_registration", "")
        if enc_date and advert_id:
            first_registration_date = _decrypt_vin(enc_date, advert_id)

        # Photo — images.photos[0].id IS the CDN URL on otomoto
        photos    = advert.get("images", {}).get("photos", [])
        photo_url = photos[0].get("id") if photos else None

        # Price
        price_from_detail = None
        price_str = (advert.get("price") or {}).get("value")
        if price_str:
            try:
                price_from_detail = parse_price(price_str)
            except ValueError:
                pass

        # Location from seller object (structure varies — guard carefully)
        location_from_detail = None
        try:
            seller = advert.get("seller") or {}
            if isinstance(seller, dict):
                loc = seller.get("location")
                if isinstance(loc, dict):
                    location_from_detail = (loc.get("city") or {}).get("name") or \
                                           (loc.get("region") or {}).get("name") or None
                elif isinstance(loc, str):
                    location_from_detail = loc or None
        except Exception:
            pass

        return {
            "year":                    year,
            "mileage_km":              mileage_km,
            "power_hp":                power_hp,
            "engine_cc":               engine_cc,
            "body_type":               body_type,
            "drivetrain":              drivetrain,
            "doors":                   doors,
            "fuel_type":               fuel_type,
            "transmission":            transmission,
            "color_ext":               color_ext,
            "vin":                     vin_found,
            "vin_confidence":          vin_confidence,
            "registration_plate":      registration_plate,
            "first_registration_date": first_registration_date,
            "photo_url":               photo_url,
            "raw_description":         description_text,
            "price_from_detail":       price_from_detail,
            "location_from_detail":    location_from_detail,
        }

    except Exception as e:
        import traceback
        print(f"    [detail error] {_safe(str(e))}")
        traceback.print_exc()
        return {}


# ── list-page card parsing ────────────────────────────────────────────────────

def _parse_otomoto_cards(soup: BeautifulSoup, page_text: str):
    """Extract cards from an otomoto.pl list page.

    Reads the urqlState GraphQL cache embedded in __NEXT_DATA__ — this gives
    clean structured data (price, location, thumbnail) without any HTML parsing.
    Falls back to article[data-id] HTML parsing if the cache isn't available.
    """
    # ── urqlState (GraphQL cache) ─────────────────────────────────────────────
    nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_text, re.S)
    if nd_m:
        try:
            nd    = json.loads(nd_m.group(1))
            urql  = nd.get("props", {}).get("pageProps", {}).get("urqlState", {})
            edges = []
            for val in urql.values():
                raw  = val.get("data") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                edges = data.get("advertSearch", {}).get("edges", [])
                if edges:
                    break

            if edges:
                cards = []
                for edge in edges:
                    node = edge.get("node", {})

                    listing_id = node.get("id")
                    title      = node.get("title", "N/A")
                    url        = node.get("url", "")

                    # Price lives in price.amount.units (integer PLN, no decimals)
                    amount     = (node.get("price") or {}).get("amount") or {}
                    units      = amount.get("units")
                    price_raw  = f"{units} zł" if units else ""

                    # Location
                    loc           = node.get("location") or {}
                    location_city = (loc.get("city") or {}).get("name") or \
                                    (loc.get("region") or {}).get("name") or None

                    # Thumbnail — prefer x1 (320×240), fall back to x2
                    thumb     = node.get("thumbnail") or {}
                    thumbnail = thumb.get("x1") or thumb.get("x2")

                    cards.append({
                        "listing_id":    listing_id,
                        "title":         title,
                        "price_raw":     price_raw,
                        "source_url":    url,
                        "thumbnail":     thumbnail,
                        "location_city": location_city,
                    })
                return cards
        except Exception:
            pass  # fall through to HTML parsing

    # ── HTML fallback (if urqlState unavailable) ──────────────────────────────
    cards = []
    for article in soup.select("article[data-id]"):
        listing_id = article.get("data-id")
        link_el    = article.select_one("a[href]")
        href       = link_el["href"] if link_el else None
        if href and href.startswith("/"):
            href = "https://www.otomoto.pl" + href

        img_el    = article.select_one("img[src]")
        thumbnail = img_el["src"] if img_el else None

        heading = article.select_one("h1, h2, h3")
        title   = heading.text.strip().split("|")[0].strip() if heading else "N/A"

        # Price — first leaf-level element with a currency symbol
        price_raw = ""
        for el in article.select("span, strong, b"):
            t = el.text.strip()
            if re.search(r"\d", t) and ("zł" in t or "PLN" in t) and len(t) < 25:
                price_raw = t
                break

        # Location — first short <p> that doesn't look like specs
        location_city = None
        for p in article.select("p"):
            t = p.text.strip()
            if t and len(t) < 60 and not re.search(r"\d{4}\s*cm|KM\b", t):
                location_city = t.split(",")[0].split(" - ")[0].strip() or None
                break

        cards.append({
            "listing_id":    listing_id,
            "title":         title,
            "price_raw":     price_raw,
            "source_url":    href,
            "thumbnail":     thumbnail,
            "location_city": location_city,
        })
    return cards


def _parse_olx_cards(soup: BeautifulSoup):
    """Extract cards from an olx.pl list page using DOM structure.

    OLX card layout (div with unique id per listing):
      <div id="listing-id">
        <a href="...">
          <img ...>             ← thumbnail
          <div>
            <h4>title</h4>      ← first h4 = title
            <p>location</p>     ← second <p> = location
            <p>price</p>        ← paragraph with price
          </div>
        </a>
      </div>
    """
    cards = []
    for item in soup.select("[data-cy='l-card']"):
        listing_id = item.get("id")

        link_el   = item.select_one("a[href]")
        href      = link_el["href"] if link_el else None
        if href and href.startswith("/"):
            href = "https://www.olx.pl" + href

        img_el    = item.select_one("img[src]")
        thumbnail = img_el["src"] if img_el else None

        # Title — first heading in the card
        heading   = item.select_one("h1, h2, h3, h4")
        title     = heading.text.strip() if heading else "N/A"

        # Price — first element with currency text
        price_raw = ""
        for el in item.select("p, span, strong"):
            t = el.text.strip()
            if re.search(r"\d", t) and ("zł" in t or "PLN" in t):
                price_raw = t
                break

        # Location — second non-empty <p> (first is usually date/category)
        location_city = None
        paragraphs = [p for p in item.select("p") if p.text.strip()]
        if len(paragraphs) >= 2:
            loc = paragraphs[1].text.strip()
            location_city = loc.split(" - ")[0].split(",")[0].strip() or None

        cards.append({
            "listing_id":    listing_id,
            "title":         title,
            "price_raw":     price_raw,
            "source_url":    href,
            "thumbnail":     thumbnail,
            "location_city": location_city,
        })
    return cards


# ── main runner ───────────────────────────────────────────────────────────────

def run(cfg: ScraperConfig, post_to_api: bool = True) -> list:
    cookies     = load_cookies()
    logged_in   = False
    if cookies:
        print(f"[auth] Cookies loaded ({len(cookies)} cookies) -- attempting token refresh...")
        cookies   = refresh_session(cookies)
        logged_in = check_session(cookies)
    else:
        print(f"[auth] No cookies -- VINs will stay encrypted.")

    results  = []
    seen_ids = set()

    list_urls = [cfg.list_url] if isinstance(cfg.list_url, str) else cfg.list_url

    for url_tmpl in list_urls:
        for page in range(1, cfg.pages + 1):
            url = url_tmpl.format(page=page)
        print(f"\n=== {cfg.make} {cfg.model} [{cfg.source}] -- Page {page} ===")

        try:
            r = requests.get(
                url, headers=HEADERS, cookies=cookies,
                timeout=15, impersonate="chrome"
            )
        except Exception as e:
            print(f"  [list error] {_safe(str(e))}")
            break

        if r.status_code != 200:
            print(f"  HTTP {r.status_code} -- stopping.")
            break

        soup = BeautifulSoup(r.text, "html.parser")

        if cfg.source == "otomoto":
            cards = _parse_otomoto_cards(soup, r.text)
        else:
            cards = _parse_olx_cards(soup)

        if not cards:
            print("  No cards found -- stopping.")
            break

        page_ids = {c["listing_id"] for c in cards}
        if page_ids and page_ids.issubset(seen_ids):
            print(f"  All {len(cards)} cards already seen -- stopping.")
            break
        seen_ids |= page_ids

        for card in cards:
            listing_id    = card["listing_id"]
            title         = card["title"]
            price_raw     = card["price_raw"]
            source_url    = card["source_url"]
            thumbnail     = card["thumbnail"]
            location_city = card["location_city"]
            price_pln     = parse_price(price_raw)

            # Title keyword guard (normalizes spaces so "C 63" matches "C63" and "E 55" matches "E55")
            if cfg.title_must_contain:
                needle = cfg.title_must_contain.lower().replace(" ", "")
                haystack = title.lower().replace(" ", "")
                if needle not in haystack:
                    print(f"  [skip] {_safe(title[:60])}")
                    continue

            print(f"  {_safe(title[:65])} | {_safe(price_raw)} | {_safe(location_city or '')}")

            detail = {}
            if source_url:
                jitter = random.uniform(0.5, 2.5)
                time.sleep(cfg.detail_delay + jitter)
                detail = fetch_detail(source_url, cookies=cookies)
                vc = detail.get("vin_confidence", "none")
                if detail.get("vin") and vc == "found_in_description":
                    print(f"    VIN (desc):   {detail['vin']}")
                elif detail.get("vin") and vc == "found_in_schema":
                    print(f"    VIN (login):  {detail['vin']}")
                elif vc == "found_in_schema" and logged_in:
                    # VIN exists but was encrypted in page — try the GraphQL reveal endpoint
                    revealed = reveal_vin(listing_id, cookies)
                    if revealed:
                        detail["vin"]            = revealed
                        detail["vin_confidence"] = "found_in_schema"
                        print(f"    VIN (api):    {revealed}")
                    else:
                        print(f"    VIN: encrypted — reveal endpoint not matched yet")
                elif vc == "found_in_schema":
                    print(f"    VIN: exists but encrypted -- not logged in")
                if detail.get("year"):
                    print(f"    {detail['year']} | {detail.get('mileage_km')} km | "
                          f"{detail.get('power_hp')} HP | {_safe(detail.get('color_ext') or '')}")
                    
                    if cfg.min_year and detail['year'] < cfg.min_year:
                        print(f"  [skip] Year {detail['year']} < min {cfg.min_year}")
                        continue
                    if cfg.max_year and detail['year'] > cfg.max_year:
                        print(f"  [skip] Year {detail['year']} > max {cfg.max_year}")
                        continue

            photo         = detail.get("photo_url") or thumbnail
            final_price   = detail.get("price_from_detail") or price_pln
            final_loc     = detail.get("location_from_detail") or location_city

            payload = {
                "source":            cfg.source,
                "source_listing_id": listing_id,
                "source_url":        source_url,
                "raw_title":         title,
                "raw_description":   detail.get("raw_description"),
                "make":              cfg.make,
                "model":             cfg.model,
                "variant":           cfg.variant,
                "year":              detail.get("year"),
                "body_type":         detail.get("body_type"),
                "engine_cc":         detail.get("engine_cc"),
                "power_hp":          detail.get("power_hp"),
                "drivetrain":        detail.get("drivetrain"),
                "doors":             detail.get("doors"),
                "fuel_type":         detail.get("fuel_type"),
                "transmission":      detail.get("transmission"),
                "color_ext":         detail.get("color_ext"),
                "price_pln":         final_price,
                "mileage_km":        detail.get("mileage_km"),
                "location_city":     final_loc,
                "photos":            [photo] if photo else [],
                "vin":               detail.get("vin"),
                "vin_confidence":    detail.get("vin_confidence", "none"),
                "registration_plate":      detail.get("registration_plate"),
                "first_registration_date": detail.get("first_registration_date"),
            }

            # Fill gaps with known model defaults
            for key, value in cfg.defaults.items():
                if not payload.get(key):
                    payload[key] = value

            # Secondary fallback for body_type from title if still missing
            if not payload.get("body_type"):
                tl = title.lower()
                if "kombi" in tl or "avant" in tl or "t-modell" in tl or "touring" in tl or "estate" in tl:
                    payload["body_type"] = "Kombi"
                elif "coupe" in tl or "coupé" in tl:
                    payload["body_type"] = "Coupe"
                elif "sedan" in tl or "limuzyna" in tl or "saloon" in tl:
                    payload["body_type"] = "Sedan"
                elif "cabrio" in tl or "kabriolet" in tl:
                    payload["body_type"] = "Kabriolet"

            results.append(payload)

            if post_to_api:
                try:
                    resp = requests.post(API_URL, json=payload, timeout=5,
                                         headers=API_HEADERS, impersonate="chrome")
                    rj   = resp.json()
                    tag  = rj.get("tag", "new" if rj.get("id", 0) > 0 else "duplicate")
                    print(f"    > SID {payload.get('source_listing_id')} API {resp.status_code} [{tag}]")
                except Exception as e:
                    print(f"    > API error: {_safe(str(e))}")

    # Sold/removed detection — mark active observations not seen this run
    if post_to_api and seen_ids:
        try:
            r = requests.post(
                f"{API_BASE}/api/mark_removed",
                json={"source": cfg.source, "make": cfg.make,
                      "model": cfg.model, "seen_ids": list(seen_ids)},
                timeout=5, headers=API_HEADERS, impersonate="chrome",
            )
            marked = r.json().get("marked", 0)
            if marked:
                print(f"[sold] {marked} listing(s) marked as removed (not seen this run).")
        except Exception:
            pass

    print(f"\nDone. {len(results)} listings processed.")
    return results
