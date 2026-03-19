"""
Shared scraping engine for OLX/Otomoto listings.
Each model scraper imports `run` from here and passes a Config.

Cookie auth
-----------
To get decrypted VINs, log into otomoto.pl in your browser, then:
  1. Open DevTools (F12) -> Application -> Cookies -> https://www.otomoto.pl
  2. Copy the values for:  laquesistoken  and  mobile_sso_token  (or similar)
  3. Save them to  scrapers/otomoto_cookies.json  in the format:
     {"laquesistoken": "xxx...", "mobile_sso_token": "yyy..."}
  The scraper loads that file automatically on each run.
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

API_URL      = "http://127.0.0.1:5555/api/ingest_pending"
HEADERS      = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
VIN_RE       = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "otomoto_cookies.json")


# ── config ────────────────────────────────────────────────────────────────────

@dataclass
class ScraperConfig:
    make:    str
    model:   str
    variant: Optional[str] = None       # e.g. "8V", "B8", "W204"

    # OLX list-page URL template — must contain {page}
    list_url: str = ""

    # When OLX has no model-specific filter (e.g. Mercedes C63 on a brand page),
    # set this to a substring that must appear in the card title (case-insensitive).
    title_must_contain: Optional[str] = None

    pages:        int   = 5
    detail_delay: float = 0.8


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    """Replace non-ASCII chars so the terminal never crashes on cp1250."""
    return text.encode("ascii", errors="replace").decode("ascii")


def parse_price(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def load_cookies() -> dict:
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


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
    try:
        r    = requests.get(url, headers=HEADERS, cookies=cookies or {}, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")

        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not nd_m:
            return {}

        nd   = json.loads(nd_m.group(1))
        blob = json.dumps(nd)

        # Key/value params — supports underscore and hyphen in key names
        params = {k: v for k, v in re.findall(
            r'"key":"([\w-]+)","label":"[^"]+","value":"([^"]+)"', blob
        )}

        year        = int(params["year"])                               if "year"         in params else None
        mileage_km  = int(re.sub(r"[^\d]", "", params["mileage"]))     if params.get("mileage") else None
        power_hp    = int(re.sub(r"[^\d]", "", params["engine_power"])) if params.get("engine_power") else None
        fuel_type   = params.get("fuel_type")
        transmission= params.get("gearbox")
        color_ext   = params.get("color")

        # Full description HTML + plain text for VIN search
        description_html = extract_description(nd)
        description_text = BeautifulSoup(description_html, "html.parser").get_text(" ") \
                           if description_html else ""

        # VIN — three sources, best to worst:
        # 1. Plain 17-char pattern in description text (always works)
        # 2. params["vin"] when logged in (otomoto decrypts it server-side)
        # 3. has_vin flag only (logged-out — confirms VIN exists but can't read it)
        vin_found      = None
        vin_confidence = "none"
        has_vin        = bool(re.search(r'"has_vin".*?"value":"1"', blob))

        for candidate in VIN_RE.findall(description_text):
            if not re.fullmatch(r"[0-9A-F]{17}", candidate):   # skip pure-hex hashes
                vin_found      = candidate
                vin_confidence = "found_in_description"
                break

        if not vin_found:
            raw_vin = params.get("vin", "")
            if raw_vin and len(raw_vin) == 17 and VIN_RE.match(raw_vin):
                vin_found      = raw_vin
                vin_confidence = "found_in_schema"
            elif has_vin:
                vin_confidence = "found_in_schema"   # encrypted — not logged in

        # Best photo from detail page (larger than list thumbnail)
        img_tags  = soup.select("img[src*='olxcdn']")
        photo_url = img_tags[0]["src"] if img_tags else None

        return {
            "year":            year,
            "mileage_km":      mileage_km,
            "power_hp":        power_hp,
            "fuel_type":       fuel_type,
            "transmission":    transmission,
            "color_ext":       color_ext,
            "vin":             vin_found,
            "vin_confidence":  vin_confidence,
            "photo_url":       photo_url,
            "raw_description": description_html,
        }

    except Exception as e:
        print(f"    [detail error] {_safe(str(e))}")
        return {}


# ── main runner ───────────────────────────────────────────────────────────────

def run(cfg: ScraperConfig, post_to_api: bool = True) -> list:
    cookies = load_cookies()
    if cookies:
        print(f"[auth] Session cookies loaded -- VINs will be decrypted if valid.")
    else:
        print(f"[auth] No cookies -- VINs will show as encrypted (found_in_schema).")

    results  = []
    seen_ids = set()

    for page in range(1, cfg.pages + 1):
        url  = cfg.list_url.format(page=page)
        print(f"\n=== {cfg.make} {cfg.model} -- Page {page} ===")
        r    = requests.get(url, headers=HEADERS, cookies=cookies)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("[data-cy='l-card']")

        if not cards:
            print("  No cards -- stopping.")
            break

        page_ids = {item.get("id") for item in cards}
        if page_ids and page_ids.issubset(seen_ids):
            print(f"  All {len(cards)} cards already seen -- stopping.")
            break
        seen_ids |= page_ids

        for item in cards:
            listing_id = item.get("id")

            title_el   = item.select_one("h4")
            price_el   = item.select_one("[data-testid='ad-price']")
            link_el    = item.select_one("a[href]")
            img_el     = item.select_one("img[src]")
            paragraphs = item.select("p")

            title     = title_el.text.strip() if title_el else "N/A"
            price_raw = price_el.text.strip()  if price_el else ""
            price_pln = parse_price(price_raw)

            href = link_el["href"] if link_el else None
            if href and href.startswith("/"):
                href = "https://www.olx.pl" + href
            source_url = href

            thumbnail = img_el["src"] if img_el else None

            location_city = None
            if len(paragraphs) >= 2:
                loc = paragraphs[1].text.strip()
                location_city = loc.split(" - ")[0].split(",")[0].strip() or None

            # Title keyword guard (used when no model-specific URL filter exists)
            if cfg.title_must_contain and \
               cfg.title_must_contain.lower() not in title.lower():
                print(f"  [skip] {_safe(title[:60])}")
                continue

            print(f"  {_safe(title[:65])} | {_safe(price_raw)} | {_safe(location_city or '')}")

            detail = {}
            if source_url:
                time.sleep(cfg.detail_delay)
                detail = fetch_detail(source_url, cookies=cookies)
                vc = detail.get("vin_confidence", "none")
                if detail.get("vin") and vc == "found_in_description":
                    print(f"    VIN (desc):   {detail['vin']}")
                elif detail.get("vin") and vc == "found_in_schema":
                    print(f"    VIN (login):  {detail['vin']}")
                elif vc == "found_in_schema":
                    print(f"    VIN: confirmed (encrypted -- add cookies to decrypt)")
                if detail.get("year"):
                    print(f"    {detail['year']} | {detail.get('mileage_km')} km | "
                          f"{detail.get('power_hp')} HP | {_safe(detail.get('color_ext') or '')}")

            photo = detail.get("photo_url") or thumbnail

            payload = {
                "source":            "olx",
                "source_listing_id": listing_id,
                "source_url":        source_url,
                "raw_title":         title,
                "raw_description":   detail.get("raw_description"),
                "make":              cfg.make,
                "model":             cfg.model,
                "variant":           cfg.variant,
                "year":              detail.get("year"),
                "power_hp":          detail.get("power_hp"),
                "fuel_type":         detail.get("fuel_type"),
                "transmission":      detail.get("transmission"),
                "color_ext":         detail.get("color_ext"),
                "price_pln":         price_pln,
                "mileage_km":        detail.get("mileage_km"),
                "location_city":     location_city,
                "photos":            [photo] if photo else [],
                "vin":               detail.get("vin"),
                "vin_confidence":    detail.get("vin_confidence", "none"),
            }

            results.append(payload)

            if post_to_api:
                try:
                    resp = requests.post(API_URL, json=payload, timeout=5)
                    rj   = resp.json()
                    tag  = "new" if rj.get("id", 0) > 0 else "duplicate"
                    print(f"    > API {resp.status_code} [{tag}]")
                except Exception as e:
                    print(f"    > API error: {_safe(str(e))}")

    print(f"\nDone. {len(results)} listings processed.")
    return results
