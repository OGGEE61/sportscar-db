"""
scrapers/olx.py
===============
Scrapes OLX.pl for performance/sports cars using the Cloudflare Browser
Rendering /crawl endpoint (headless browser, returns Markdown per page).

Usage:
    python scrapers/olx.py                     # all brands
    python scrapers/olx.py BMW                 # single brand
    python scrapers/olx.py BMW m3              # single model
    python scrapers/olx.py BMW m3 --dry-run    # preview without POSTing

Requires environment variables (see .env.example):
    CF_ACCOUNT_ID, CF_BR_API_TOKEN
"""

import os
import re
import sys
import json
import time
import logging
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

CF_ACCOUNT_ID  = os.getenv("CF_ACCOUNT_ID", "")
CF_BR_API_TOKEN = os.getenv("CF_BR_API_TOKEN", "")

CRAWL_BASE = (
    "https://api.cloudflare.com/client/v4/accounts"
    "/{account_id}/browser-rendering/crawl"
)

FLASK_INGEST_URL = "http://127.0.0.1:5555/api/ingest_pending"

POLL_INTERVAL  = 5      # seconds between status polls
CRAWL_TIMEOUT  = 1200   # seconds before giving up on a crawl job
CRAWL_LIMIT    = 100    # max pages per model crawl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("olx")

# ─────────────────────────────────────────────────────────────────────────────
# Targets
# ─────────────────────────────────────────────────────────────────────────────

# Brand name → list of OLX model filter slugs
TARGETS: dict[str, list[str]] = {
    "BMW":          ["m2", "m3", "m4", "m5", "m6", "m8",
                     "x3-m", "x4-m", "x5-m", "x6-m"],
    "Mercedes-AMG": ["a45", "cla45", "c63", "e63", "s63",
                     "sls-amg", "amg-gt", "gle63", "gls63", "gl63"],
    "Audi":         ["rs3", "rs4", "rs5", "rs6", "rs7", "r8", "tt-rs",
                     "s3", "s4", "s5", "s6", "s7", "sq5", "sq7",
                     "rs-q3", "rs-q3-sportback", "rs-q8"],
    "Porsche":      ["911", "boxster", "cayman", "panamera", "cayenne", "macan"],
    "VW":           ["golf-r", "gti", "r32", "scirocco-r"],
}

# Brand name → OLX make slug used in URL paths
MAKE_SLUGS: dict[str, str] = {
    "BMW":          "bmw",
    "Mercedes-AMG": "mercedes-benz",
    "Audi":         "audi",
    "Porsche":      "porsche",
    "VW":           "volkswagen",
}

# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

VIN_RE   = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
PRICE_RE = re.compile(r'(\d[\d\s]{2,9})\s*(zł|PLN)', re.IGNORECASE)
MILE_RE  = re.compile(r'(\d[\d\s]{1,7})\s*km')  # case-sensitive: lowercase km=kilometers, KM=horsepower in Polish
YEAR_RE  = re.compile(r'\b(198[5-9]|199\d|20[0-3]\d)\b')  # 1985-2039: covers all M-car generations
ID_RE    = re.compile(r'ID([A-Za-z0-9]+)\.html')


# ─────────────────────────────────────────────────────────────────────────────
# URL builders
# ─────────────────────────────────────────────────────────────────────────────

def olx_search_url(brand: str, model: str) -> str:
    """Build OLX.pl search URL for a brand + model combination."""
    make_slug = MAKE_SLUGS[brand]
    return (
        f"https://www.olx.pl/motoryzacja/samochody/{make_slug}/"
        f"?search%5Bfilter_enum_model%5D%5B0%5D={model}"
    )


def _crawl_url(job_id: str = "") -> str:
    base = CRAWL_BASE.format(account_id=CF_ACCOUNT_ID)
    return f"{base}/{job_id}" if job_id else base


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {CF_BR_API_TOKEN}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Crawl API
# ─────────────────────────────────────────────────────────────────────────────

def submit_crawl(url: str) -> str:
    """POST a crawl job and return the job_id."""
    make_slug = next(
        (s for s in MAKE_SLUGS.values() if f"/{s}/" in url),
        "samochody",
    )
    payload = {
        "url": url,
        "limit": CRAWL_LIMIT,
        "depth": 2,
        "formats": ["markdown"],
        "render": True,
        "source": "links",
        "rejectResourceTypes": ["image", "media", "font", "stylesheet"],
        "gotoOptions": {"waitUntil": "networkidle2", "timeout": 60000},
        "options": {
            "includePatterns": [
                f"https://www.olx.pl/motoryzacja/samochody/{make_slug}/**",
                "https://www.olx.pl/d/oferta/**",
            ],
            "excludePatterns": [],
        },
    }
    resp = requests.post(_crawl_url(), json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Crawl submit failed: {data.get('errors')}")
    job_id: str = data["result"]
    log.info("Crawl job submitted: %s", job_id)
    return job_id


def poll_crawl(job_id: str, timeout_secs: int = CRAWL_TIMEOUT) -> list[dict]:
    """
    Poll until the crawl job reaches a terminal status, then fetch and
    return all records (handles pagination for results > 10 MB).
    """
    terminal = {"completed", "errored", "cancelled_due_to_timeout",
                "cancelled_due_to_limits", "cancelled_by_user"}

    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        resp = requests.get(
            _crawl_url(job_id),
            params={"limit": 1},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("result", {}).get("status", "running")
        log.info("  Crawl status: %s", status)
        if status in terminal:
            break
        time.sleep(POLL_INTERVAL)
    else:
        raise TimeoutError(f"Crawl job {job_id} did not finish within {timeout_secs}s")

    if status != "completed":
        log.warning("Crawl job %s ended with status: %s", job_id, status)
        return []

    # Fetch all records with cursor-based pagination
    records: list[dict] = []
    params: dict = {"status": "completed"}
    while True:
        resp = requests.get(
            _crawl_url(job_id),
            params=params,
            headers=_headers(),
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("result", {}).get("records", [])
        records.extend(batch)
        cursor = data.get("result", {}).get("cursor")
        if not cursor:
            break
        params["cursor"] = cursor

    log.info("  Crawl fetched %d records", len(records))
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Markdown parsing
# ─────────────────────────────────────────────────────────────────────────────

def _digits(text: str) -> int | None:
    """Strip whitespace/non-digits and return int, or None."""
    clean = re.sub(r"[^\d]", "", text)
    return int(clean) if clean else None


def parse_listing_from_markdown(record: dict) -> dict | None:
    """
    Parse one crawl record into a listing dict for /api/ingest_pending.
    Returns None if the record is a search results page, not a listing detail.
    """
    url = record.get("url", "")

    # Skip search results pages — keep only individual listing detail pages
    if "/d/oferta/" not in url and "/oferta/" not in url:
        return None

    # Skip errored / blocked records
    rec_status = record.get("status")
    if rec_status not in (None, 200, "200", "completed"):
        log.debug("  skip %s (status=%s)", url, rec_status)
        return None

    markdown = record.get("markdown") or ""
    metadata = record.get("metadata") or {}
    title = metadata.get("title") or ""

    # source_listing_id — OLX URLs end in ID{id}.html
    m = ID_RE.search(url)
    source_listing_id = m.group(1) if m else None

    # Price (PLN)
    price_pln = None
    pm = PRICE_RE.search(markdown)
    if pm:
        price_pln = _digits(pm.group(1))

    # Mileage
    mileage_km = None
    mm = MILE_RE.search(markdown)
    if mm:
        mileage_km = _digits(mm.group(1))

    # Year (first plausible 4-digit year)
    year = None
    ym = YEAR_RE.search(markdown)
    if ym:
        year = int(ym.group(1))

    # VIN
    vin = None
    vin_confidence = "none"
    vm = VIN_RE.search(markdown.upper())
    if vm:
        vin = vm.group()
        vin_confidence = "found_in_description"

    # Location: look for "Lokalizacja" or "Miejsce" label in markdown
    location_city = None
    location_region = None
    loc_m = re.search(
        r'(?:Lokalizacja|Miejsce|Location)[:\s]*([^\n,]+)(?:,\s*([^\n]+))?',
        markdown, re.IGNORECASE
    )
    if loc_m:
        location_city = loc_m.group(1).strip() or None
        location_region = (loc_m.group(2) or "").strip() or None

    # Seller type
    lower_md = markdown.lower()
    seller_type = "private"
    if any(kw in lower_md for kw in ("dealer", "firma", "salon", "komisem", "komis")):
        seller_type = "dealer"

    return {
        "source":             "olx",
        "source_listing_id":  source_listing_id,
        "source_url":         url,
        "raw_title":          title,
        "raw_description":    markdown[:4000],  # cap to avoid DB column limits
        "photos":             [],
        "make":               None,   # injected by scrape_model after parsing
        "model":              None,
        "variant":            None,
        "year":               year,
        "body_type":          None,
        "engine_cc":          None,
        "power_hp":           None,
        "fuel_type":          None,
        "drivetrain":         None,
        "transmission":       None,
        "color_ext":          None,
        "doors":              None,
        "price_pln":          price_pln,
        "price_eur":          None,
        "mileage_km":         mileage_km,
        "location_city":      location_city,
        "location_region":    location_region,
        "seller_type":        seller_type,
        "seller_name":        None,
        "vin":                vin,
        "vin_confidence":     vin_confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ingest
# ─────────────────────────────────────────────────────────────────────────────

def ingest(listing: dict, dry_run: bool = False) -> None:
    """POST a parsed listing to Flask /api/ingest_pending."""
    if dry_run:
        sys.stdout.buffer.write(
            json.dumps(listing, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        return
    try:
        r = requests.post(FLASK_INGEST_URL, json=listing, timeout=10)
        result = r.json()
        if result.get("status") == "ok":
            log.info("    posted → pending id=%s", result.get("id"))
        else:
            log.warning("    ingest response: %s", result)
    except Exception as e:
        log.error("    POST failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Scrape helpers
# ─────────────────────────────────────────────────────────────────────────────

def scrape_model(brand: str, model: str, dry_run: bool = False) -> None:
    """Crawl one brand + model, parse all listing records, ingest each."""
    log.info("[%s / %s] submitting crawl", brand, model)
    url = olx_search_url(brand, model)
    try:
        job_id = submit_crawl(url)
        records = poll_crawl(job_id)
    except Exception as e:
        log.error("[%s / %s] crawl failed: %s", brand, model, e)
        return

    ingested = 0
    for record in records:
        listing = parse_listing_from_markdown(record)
        if listing is None:
            continue
        # Inject brand/model context
        listing["make"] = brand
        listing["model"] = model
        ingest(listing, dry_run=dry_run)
        ingested += 1

    log.info("[%s / %s] ingested %d listings", brand, model, ingested)


def scrape_brand(brand: str, dry_run: bool = False) -> None:
    """Iterate all models for one brand."""
    models = TARGETS.get(brand)
    if not models:
        log.error("Unknown brand: %s  (valid: %s)", brand, list(TARGETS))
        return
    for model in models:
        scrape_model(brand, model, dry_run=dry_run)


def scrape_all(dry_run: bool = False) -> None:
    """Iterate all brands and models."""
    for brand in TARGETS:
        scrape_brand(brand, dry_run=dry_run)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    if len(args) == 2:
        scrape_model(args[0], args[1], dry_run)   # e.g. BMW m3
    elif len(args) == 1:
        scrape_brand(args[0], dry_run)             # e.g. BMW
    else:
        scrape_all(dry_run)                        # no args → all brands
