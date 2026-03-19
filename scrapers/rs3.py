"""
Audi RS3 scraper — OLX/Otomoto listing page.
List page lives on OLX but cards link to otomoto.pl detail pages.

For each listing we:
  1. Grab card-level data (title, price, thumbnail, location) from the list page.
  2. Fetch the detail page to extract structured params (year, mileage, power,
     fuel, transmission, colour) from __NEXT_DATA__ JSON.
  3. Search the description text for a 17-char VIN pattern.
  4. POST the enriched payload to /api/ingest_pending.
"""

import re
import json
import time
import requests
from bs4 import BeautifulSoup

API_URL  = "http://127.0.0.1:5555/api/ingest_pending"
LIST_URL = (
    "https://www.olx.pl/motoryzacja/samochody/q-audi-rs3/"
    "?search%5Bfilter_enum_model%5D%5B0%5D=rs3&page={page}"
)
HEADERS  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
VIN_RE   = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")


# ── helpers ───────────────────────────────────────────────────────────────────

def parse_price(text):
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def fetch_detail(url):
    """
    Fetch an otomoto.pl detail page and return a dict with enriched fields.
    Returns {} on failure.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # ── __NEXT_DATA__ params ──────────────────────────────────────────────
        nd_match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S
        )
        if not nd_match:
            return {}

        blob = nd_match.group(1)

        # Extract all {key, value} param pairs
        params = {}
        for k, v in re.findall(
            r'"key":"(\w+)","label":"[^"]+","value":"([^"]+)"', blob
        ):
            params[k] = v

        year         = int(params["year"])           if "year"         in params else None
        mileage_raw  = re.sub(r"[^\d]", "", params.get("mileage", ""))
        mileage_km   = int(mileage_raw)              if mileage_raw    else None
        power_raw    = re.sub(r"[^\d]", "", params.get("engine_power", ""))
        power_hp     = int(power_raw)                if power_raw      else None
        fuel_type    = params.get("fuel_type")
        transmission = params.get("gearbox")
        color_ext    = params.get("color")

        # ── VIN search ────────────────────────────────────────────────────────
        # 1. Try description element
        desc_el = soup.find(attrs={"data-testid": "content-description-value"})
        desc_text = desc_el.get_text(" ") if desc_el else ""

        # 2. Also search the raw blob (some sellers embed VIN in structured text)
        combined = desc_text + " " + blob

        vin_found = None
        vin_confidence = "none"

        # Check if site confirms VIN exists
        has_vin = bool(re.search(r'"has_vin".*?"value":"1"', blob))

        # Try plain-text VIN in description
        for candidate in VIN_RE.findall(desc_text):
            # Basic VIN checksum heuristic: reject strings that look like hex hashes
            if not re.fullmatch(r"[0-9A-F]{17}", candidate):
                vin_found = candidate
                vin_confidence = "found_in_description"
                break

        # ── Best photo ────────────────────────────────────────────────────────
        # Prefer the large CDN image from the page, not the tiny thumbnail
        img_tags = soup.select("img[src*='olxcdn']")
        photo_url = img_tags[0]["src"] if img_tags else None

        return {
            "year":         year,
            "mileage_km":   mileage_km,
            "power_hp":     power_hp,
            "fuel_type":    fuel_type,
            "transmission": transmission,
            "color_ext":    color_ext,
            "vin":          vin_found,
            "vin_confidence": vin_confidence if vin_found else ("found_in_schema" if has_vin else "none"),
            "photo_url":    photo_url,
            "desc_snippet": desc_text[:300] if desc_text else None,
        }

    except Exception as e:
        print(f"    [detail error] {e}")
        return {}


# ── main scraper ──────────────────────────────────────────────────────────────

def scrape_rs3(pages=3, post_to_api=True, detail_delay=1.0):
    results = []

    for page in range(1, pages + 1):
        url = LIST_URL.format(page=page)
        print(f"\n=== Page {page} ===")
        r = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("[data-cy='l-card']")
        print(f"  {len(cards)} cards found")

        for item in cards:
            title_el  = item.select_one("h4")
            price_el  = item.select_one("[data-testid='ad-price']")
            link_el   = item.select_one("a[href]")
            img_el    = item.select_one("img[src]")
            paragraphs = item.select("p")

            title     = title_el.text.strip()  if title_el  else "N/A"
            price_raw = price_el.text.strip()   if price_el  else ""
            price_pln = parse_price(price_raw)
            href = link_el["href"] if link_el else None
            if href and href.startswith("/"):
                href = "https://www.olx.pl" + href
            source_url = href
            source_listing_id = item.get("id")
            thumbnail         = img_el["src"]    if img_el   else None

            location_city = None
            if len(paragraphs) >= 2:
                loc = paragraphs[1].text.strip()
                location_city = loc.split(" - ")[0].split(",")[0].strip() or None

            print(f"  {title[:60]} | {price_raw} | {location_city}")

            # ── Fetch detail page ─────────────────────────────────────────────
            detail = {}
            if source_url:
                time.sleep(detail_delay)
                detail = fetch_detail(source_url)
                if detail.get("vin"):
                    print(f"    VIN found: {detail['vin']} ({detail['vin_confidence']})")
                elif detail.get("vin_confidence") == "found_in_schema":
                    print(f"    VIN confirmed by site (encrypted)")
                if detail.get("year"):
                    print(f"    {detail['year']} | {detail.get('mileage_km')} km | {detail.get('power_hp')} HP")

            photo = detail.get("photo_url") or thumbnail

            payload = {
                "source":             "olx",
                "source_listing_id":  source_listing_id,
                "source_url":         source_url,
                "raw_title":          title,
                "make":               "Audi",
                "model":              "RS3",
                "year":               detail.get("year"),
                "power_hp":           detail.get("power_hp"),
                "fuel_type":          detail.get("fuel_type"),
                "transmission":       detail.get("transmission"),
                "color_ext":          detail.get("color_ext"),
                "price_pln":          price_pln,
                "mileage_km":         detail.get("mileage_km"),
                "location_city":      location_city,
                "photos":             [photo] if photo else [],
                "vin":                detail.get("vin"),
                "vin_confidence":     detail.get("vin_confidence", "none"),
                "raw_description":    detail.get("desc_snippet"),
            }

            results.append(payload)

            if post_to_api:
                try:
                    resp = requests.post(API_URL, json=payload, timeout=5)
                    rj = resp.json()
                    status = "new" if rj.get("id", 0) > 0 else "duplicate"
                    print(f"    > API {resp.status_code} [{status}]")
                except Exception as e:
                    print(f"    > API error: {e}")

    print(f"\nDone. {len(results)} listings processed.")
    return results


if __name__ == "__main__":
    scrape_rs3(pages=3, post_to_api=True, detail_delay=0.8)
