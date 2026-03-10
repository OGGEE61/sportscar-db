"""
scrapers/olx.py
===============
Scrapes OLX.pl for German performance/sports cars and posts each listing
to the local /api/ingest_pending endpoint for manual review.

Usage:
    python scrapers/olx.py              # all targets
    python scrapers/olx.py bmw m3       # single target (make slug, model slug)
    python scrapers/olx.py --dry-run    # print what would be scraped, don't POST

Requires:
    pip install requests beautifulsoup4
"""

import requests
import json
import re
import sys
import time
import random
import logging
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL    = "https://www.olx.pl"
INGEST_URL  = "http://127.0.0.1:5555/api/ingest_pending"
YEAR_FROM   = 1990
YEAR_TO     = 2020
MAX_PAGES   = 10          # max pages to scrape per target (20 listings/page)
DELAY_MIN   = 0.5         # seconds between requests (human-like)
DELAY_MAX   = 1.5

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("olx")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─────────────────────────────────────────────────────────────────────────────
# Targets  (make_slug, model_slug, keywords_that_must_appear_in_title)
# OLX model slugs for Polish site. Adjust if any return 0 results.
# ─────────────────────────────────────────────────────────────────────────────

# (make_slug, olx_model_slug, keywords_to_verify_in_title)
# OLX model slugs confirmed from URL pattern:
# /motoryzacja/samochody/{make}/?search[filter_enum_model][0]={model_slug}
TARGETS = [
    # BMW M-division
    ("bmw", "m2",   ["M2"]),
    ("bmw", "m3",   ["M3"]),
    ("bmw", "m4",   ["M4"]),
    ("bmw", "m5",   ["M5"]),
    ("bmw", "m6",   ["M6"]),
    ("bmw", "m8",   ["M8"]),
    ("bmw", "x3-m", ["X3M", "X3 M"]),
    ("bmw", "x4-m", ["X4M", "X4 M"]),
    ("bmw", "x5-m", ["X5M", "X5 M"]),
    ("bmw", "x6-m", ["X6M", "X6 M"]),

    # Mercedes-AMG
    ("mercedes-benz", "klasa-a",   ["A45", "A 45"]),
    ("mercedes-benz", "cla",       ["CLA45", "CLA 45"]),
    ("mercedes-benz", "klasa-c",   ["C63", "C 63"]),
    ("mercedes-benz", "klasa-e",   ["E63", "E 63"]),
    ("mercedes-benz", "klasa-s",   ["S63", "S 63"]),
    ("mercedes-benz", "sls-amg",   ["SLS"]),
    ("mercedes-benz", "amg-gt",    ["AMG GT"]),
    ("mercedes-benz", "gle",       ["GLE 63", "GLE63", "GLE AMG"]),
    ("mercedes-benz", "gls",       ["GLS 63", "GLS63", "GLS AMG"]),
    ("mercedes-benz", "gl",        ["GL 63", "GL63"]),

    # Audi RS / S
    ("audi", "rs3",            ["RS3", "RS 3"]),
    ("audi", "rs4",            ["RS4", "RS 4"]),
    ("audi", "rs5",            ["RS5", "RS 5"]),
    ("audi", "rs6",            ["RS6", "RS 6"]),
    ("audi", "rs7",            ["RS7", "RS 7"]),
    ("audi", "r8",             ["R8"]),
    ("audi", "tt-rs",          ["TT RS", "TTRS"]),
    ("audi", "s3",             ["S3"]),
    ("audi", "s4",             ["S4"]),
    ("audi", "s5",             ["S5"]),
    ("audi", "s6",             ["S6"]),
    ("audi", "s7",             ["S7"]),
    ("audi", "sq5",            ["SQ5"]),
    ("audi", "sq7",            ["SQ7"]),
    ("audi", "rs-q3",          ["RS Q3"]),
    ("audi", "rs-q3-sportback",["RS Q3", "RSQ3"]),
    ("audi", "rs-q8",          ["RS Q8", "RSQ8"]),

    # Porsche
    ("porsche", "911",      ["911"]),
    ("porsche", "boxster",  ["Boxster"]),
    ("porsche", "cayman",   ["Cayman"]),
    ("porsche", "panamera", ["Panamera"]),
    ("porsche", "cayenne",  ["Cayenne"]),
    ("porsche", "macan",    ["Macan"]),

    # VW performance
    ("volkswagen", "golf",     ["Golf R", "GTI R32", "R32"]),
    ("volkswagen", "scirocco", ["Scirocco R"]),
]

# ─────────────────────────────────────────────────────────────────────────────
# OLX HTML attribute label → our field name
# ─────────────────────────────────────────────────────────────────────────────

PL_PARAM_MAP = {
    "rok produkcji":     "year",
    "przebieg":          "mileage_km",
    "pojemność skokowa": "engine_cc",
    "moc":               "power_hp",
    "rodzaj paliwa":     "fuel_type",
    "skrzynia biegów":   "transmission",
    "napęd":             "drivetrain",
    "kolor":             "color_ext",
    "typ nadwozia":      "body_type",
    "liczba drzwi":      "doors",
    "stan":              "condition",
}

VIN_RE    = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
POWER_RE  = re.compile(r'(\d{2,4})\s*(?:KM|HP|PS|cv)', re.IGNORECASE)
ENGINE_RE = re.compile(r'(\d+)[.,](\d)\s*(?:l\b|litr|L\b)?', re.IGNORECASE)
MILE_RE   = re.compile(r'(\d[\d\s]{2,7})\s*km', re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def get(session, url, **kwargs):
    """GET with random human-like delay, retry once on failure."""
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    try:
        r = session.get(url, timeout=15, **kwargs)
        r.raise_for_status()
        r.encoding = "utf-8"   # force UTF-8 — OLX is always UTF-8
        return r
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except requests.RequestException as e:
        log.warning("Request failed (%s), retrying in 10s…", e)
        time.sleep(10)
        r = session.get(url, timeout=20, **kwargs)
        r.raise_for_status()
        r.encoding = "utf-8"
        return r


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_jsonld(soup):
    """Extract all schema.org data from JSON-LD script tags."""
    result = {}
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        schema_type = data.get("@type", "")

        if schema_type in ("Car", "Vehicle", "MotorizedVehicle"):
            brand = data.get("brand", {})
            result["make"]      = brand.get("name") if isinstance(brand, dict) else brand
            result["model"]     = data.get("model")
            result["body_type"] = data.get("bodyType")
            result["color_ext"] = data.get("color")

            year = data.get("productionDate") or data.get("modelDate")
            result["year"] = int(str(year)[:4]) if year else None

            vin = data.get("vehicleIdentificationNumber", "").strip().upper()
            if vin and len(vin) == 17 and VIN_RE.fullmatch(vin):
                result["vin"]            = vin
                result["vin_confidence"] = "found_in_schema"

            result["description"] = data.get("description", "")

            images = data.get("image", [])
            result["photos"] = ([images] if isinstance(images, str) else images)

            offers = data.get("offers", {})
            if isinstance(offers, dict):
                result["price_pln"] = offers.get("price")

            area = data.get("areaServed", {})
            if isinstance(area, dict):
                result["location_city"] = area.get("name")
            elif isinstance(area, str):
                result["location_city"] = area

        elif schema_type == "Product":
            result["source_listing_id"] = str(data.get("sku") or data.get("productID") or "")
            if not result.get("photos"):
                images = data.get("image", [])
                result["photos"] = [images] if isinstance(images, str) else images

    return result


def parse_params(soup):
    """Extract structured parameters from the OLX listing HTML."""
    params = {}

    # Strategy 1: data-testid based (current OLX structure)
    container = (
        soup.find(attrs={"data-testid": "ad-params-container"}) or
        soup.find(attrs={"data-testid": "ad-params"}) or
        soup.find(attrs={"data-testid": "ad-details"})
    )
    if container:
        for item in container.find_all("li"):
            texts = [p.get_text(strip=True) for p in item.find_all(["p", "span", "strong"])]
            if len(texts) >= 2:
                label = texts[0].lower().rstrip(":")
                value = texts[1]
                field = PL_PARAM_MAP.get(label)
                if field:
                    params[field] = value

    # Strategy 2: look for any <li> with two adjacent <p> tags (label + value)
    if not params:
        for li in soup.find_all("li"):
            ps = li.find_all("p", recursive=False)
            if len(ps) == 2:
                label = ps[0].get_text(strip=True).lower().rstrip(":")
                value = ps[1].get_text(strip=True)
                field = PL_PARAM_MAP.get(label)
                if field:
                    params[field] = value

    return params


def clean_params(raw):
    """Coerce extracted HTML param strings to the right Python types."""
    out = {}
    for field, val in raw.items():
        if not val:
            continue
        val = str(val).strip()
        if field == "mileage_km":
            digits = re.sub(r"[^\d]", "", val)
            out[field] = int(digits) if digits else None
        elif field == "engine_cc":
            digits = re.sub(r"[^\d]", "", val)
            out[field] = int(digits) if digits else None
        elif field == "power_hp":
            m = re.search(r"(\d+)", val)
            out[field] = int(m.group(1)) if m else None
        elif field == "year":
            m = re.search(r"(\d{4})", val)
            out[field] = int(m.group(1)) if m else None
        elif field == "doors":
            m = re.search(r"(\d+)", val)
            out[field] = int(m.group(1)) if m else None
        elif field == "transmission":
            v = val.lower()
            if "automat" in v:
                out[field] = "automatic"
            elif "manual" in v or "ręczna" in v:
                out[field] = "manual"
            else:
                out[field] = val
        elif field == "drivetrain":
            v = val.lower()
            if "4x4" in v or "4wd" in v or "awd" in v or "quattro" in v or "xdrive" in v:
                out[field] = "AWD"
            elif "rwd" in v or "tylny" in v or "tył" in v:
                out[field] = "RWD"
            elif "fwd" in v or "przód" in v:
                out[field] = "FWD"
            else:
                out[field] = val
        elif field == "fuel_type":
            v = val.lower()
            if "benzyn" in v or "petrol" in v:
                out[field] = "petrol"
            elif "diesel" in v:
                out[field] = "diesel"
            elif "hybrid" in v:
                out[field] = "hybrid"
            elif "elektr" in v:
                out[field] = "electric"
            else:
                out[field] = val
        else:
            out[field] = val
    return out


def scan_description_for_vin(text):
    """Return first valid-looking VIN found in free text."""
    if not text:
        return None
    for m in VIN_RE.finditer(text.upper()):
        candidate = m.group()
        # Basic VIN sanity: no I, O, Q, must be 17 chars
        if len(candidate) == 17:
            return candidate
    return None


def extract_seller_type(soup):
    """Detect private vs dealer from page."""
    page_text = soup.get_text(" ", strip=True).lower()
    if "dealer" in page_text or "firma" in page_text or "salon" in page_text:
        return "dealer"
    return "private"


# ─────────────────────────────────────────────────────────────────────────────
# Search result parsing
# ─────────────────────────────────────────────────────────────────────────────

def get_listing_urls(soup):
    """Extract OLX listing URLs from a rendered search results page.

    Primary: data-cy='l-card' cards (confirmed selector as of 2025).
    Fallback: any <a href> containing /d/oferta/.
    Only returns olx.pl URLs — skips aggregated otomoto.pl cards.
    """
    urls = set()

    def is_olx_url(url):
        return "olx.pl/d/oferta/" in url or "olx.pl/oferta/" in url

    # Primary: listing cards identified by data-cy="l-card"
    for card in soup.select("[data-cy='l-card']"):
        link = card if card.name == "a" else card.find("a", href=True)
        if link and link.get("href"):
            href = link["href"]
            full = href if href.startswith("http") else BASE_URL + href
            if is_olx_url(full):
                urls.add(full.split("?")[0])   # strip tracking params

    # Fallback: any anchor with /d/oferta/ in the href
    if not urls:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/d/oferta/" in href:
                full = href if href.startswith("http") else BASE_URL + href
                if is_olx_url(full):
                    urls.add(full.split("?")[0])

    return list(urls)


# ─────────────────────────────────────────────────────────────────────────────
# Listing scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_listing(session, url):
    """Fetch one listing page and return a dict ready for /api/ingest_pending."""
    resp = get(session, url)
    if resp is None:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    jld   = parse_jsonld(soup)
    praw  = parse_params(soup)
    pclean = clean_params(praw)

    # Merge: JSON-LD wins where it has data, HTML params fill in the rest
    def pick(field, fallback=None):
        return jld.get(field) or pclean.get(field) or fallback

    description = jld.get("description", "")

    # VIN: schema > description scan
    vin            = jld.get("vin")
    vin_confidence = jld.get("vin_confidence", "none")
    if not vin:
        vin = scan_description_for_vin(description)
        if vin:
            vin_confidence = "found_in_description"

    # Year filter – skip if outside our range
    year = pick("year") or pclean.get("year")
    if year and (int(year) < YEAR_FROM or int(year) > YEAR_TO):
        log.debug("  skip year %s out of range", year)
        return None

    # Extract listing ID from URL  (…-IDxxxxxxx.html)
    listing_id_match = re.search(r'-ID([A-Za-z0-9]+)\.html', url)
    source_listing_id = jld.get("source_listing_id") or (
        listing_id_match.group(1) if listing_id_match else None
    )

    # Seller info
    seller_type = extract_seller_type(soup)

    return {
        "source":             "olx",
        "source_listing_id":  source_listing_id,
        "source_url":         url,
        "raw_title":          soup.title.string.strip() if soup.title else "",
        "raw_description":    description,
        "photos":             jld.get("photos", []),
        "make":               pick("make"),
        "model":              pick("model"),
        "variant":            None,
        "year":               year,
        "body_type":          pick("body_type"),
        "engine_cc":          pick("engine_cc"),
        "power_hp":           pick("power_hp"),
        "fuel_type":          pick("fuel_type"),
        "drivetrain":         pick("drivetrain"),
        "transmission":       pick("transmission"),
        "color_ext":          pick("color_ext"),
        "doors":              pick("doors"),
        "price_pln":          pick("price_pln"),
        "price_eur":          None,
        "mileage_km":         pick("mileage_km"),
        "location_city":      pick("location_city"),
        "location_region":    None,
        "seller_type":        seller_type,
        "seller_name":        None,
        "vin":                vin,
        "vin_confidence":     vin_confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Target scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_target(session, make_slug, model_slug, keywords, dry_run=False, ingest_session=None):
    # Confirmed: float year filter, enum model, page param
    def build_url(page=1):
        return (
            f"{BASE_URL}/motoryzacja/samochody/{make_slug}/"
            f"?search%5Bfilter_enum_model%5D%5B0%5D={model_slug}"
            f"&search%5Bfilter_float_year%3Afrom%5D={YEAR_FROM}"
            f"&search%5Bfilter_float_year%3Ato%5D={YEAR_TO}"
            f"&page={page}"
        )

    total_posted = 0
    seen_urls = set()    # track across pages to detect when OLX stops returning new ones

    for page in range(1, MAX_PAGES + 1):
        url = build_url(page)
        log.info("[%s/%s] page %d", make_slug, model_slug, page)

        resp = get(session, url)
        if resp is None:
            log.warning("  404 — skipping %s/%s", make_slug, model_slug)
            return total_posted

        soup = BeautifulSoup(resp.text, "html.parser")
        listing_urls = get_listing_urls(soup)

        if not listing_urls:
            log.info("  no listings on page %d, stopping", page)
            break

        # Stop if OLX is cycling the same listings (happens after last real page)
        new_urls = [u for u in listing_urls if u not in seen_urls]
        if not new_urls:
            log.info("  no new URLs on page %d, pagination exhausted", page)
            break
        seen_urls.update(new_urls)
        log.info("  %d new listing URLs (page %d)", len(new_urls), page)

        for listing_url in new_urls:
            log.info("    scraping %s", listing_url)
            data = scrape_listing(session, listing_url)

            if data is None:
                continue

            # Keyword check: title must mention the model we're searching for
            title_check = (data.get("raw_title") or "").upper()
            if keywords and not any(kw.upper() in title_check for kw in keywords):
                log.info("    skip (keyword mismatch) — %s", (data.get("raw_title") or "")[:60])
                continue

            if dry_run:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                try:
                    poster = ingest_session or requests
                    r = poster.post(INGEST_URL, json=data, timeout=10)
                    result = r.json()
                    if result.get("status") == "ok" and result.get("id"):
                        log.info("    posted → pending id=%s", result["id"])
                        total_posted += 1
                    elif result.get("id") == 0 or "already exists" in str(result):
                        log.debug("    duplicate, skipped")
                    else:
                        log.warning("    ingest error: %s", result)
                except Exception as e:
                    log.error("    POST failed: %s", e)

    return total_posted


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    # Optional: single target  e.g.  python scrapers/olx.py bmw m3
    if len(args) == 2:
        targets = [(args[0], args[1], [])]
    else:
        targets = TARGETS

    session = make_session()
    ingest_session = requests.Session()  # persistent connection to local Flask server
    grand_total = 0

    for make_slug, model_slug, keywords in targets:
        try:
            n = scrape_target(session, make_slug, model_slug, keywords,
                              dry_run=dry_run, ingest_session=ingest_session)
            grand_total += n
        except KeyboardInterrupt:
            log.info("Interrupted.")
            break
        except Exception as e:
            log.error("Error on %s/%s: %s", make_slug, model_slug, e)

    log.info("Done. Total listings posted: %d", grand_total)


if __name__ == "__main__":
    main()
