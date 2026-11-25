"""Local registration plate detection (YOLOv8 + fast-plate-ocr).

Finds registration plates in car photos, crops a close-up, reads the number,
and saves the proposals to the human-in-the-loop review queue (`plate_review_queue`).
"""

import os
import re
import io
import json
import base64
import sqlite3
import urllib.request
from typing import List, Dict, Optional
from PIL import Image
import numpy as np


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

MODEL_PATH = os.path.join(BASE_DIR, "models", "yolov8n_license_plate.pt")
CROPS_DIR = os.path.join(BASE_DIR, "static", "plate_crops")
DB_PATH = os.path.join(BASE_DIR, "sportscar_market.db")

os.makedirs(CROPS_DIR, exist_ok=True)

# Words on plate frames and dealer / advertising plates, to filter out
DEALER_WORDS = {
    "OTOMOTO", "OLX", "KOMIS", "SALON", "AUTOPLUS", "VIP", "CAR",
    "DEALER", "SERVICE", "BMW", "AUDI", "MERCEDES", "PORSCHE", "AUTA",
    "POZNAN", "WARSZAWA", "KRAKOW", "WROCLAW", "GDANSK", "POLSKA", "PL"
}

# Plate model: on 97 plates corrected by a human it read 89 without error (EasyOCR: 9)
OCR_MODEL = "cct-s-v2-global-model"
# Lowest per-character confidence for a reading to become a proposal; keeps every correct
# reading from that test and drops almost half of the frames and lettering
OCR_MIN_CONFIDENCE = 0.7

_yolo_model = None
_plate_reader = None


def get_models():
    """Load the models lazily, so importing the module costs no memory."""
    global _yolo_model, _plate_reader
    # CV and OCR engines are imported only here, so the module loads without them
    from ultralytics import YOLO
    from fast_plate_ocr import LicensePlateRecognizer
    if _yolo_model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Brak pliku wag modelu: {MODEL_PATH}")
        _yolo_model = YOLO(MODEL_PATH)
    if _plate_reader is None:
        _plate_reader = LicensePlateRecognizer(OCR_MODEL, device="cpu")
    return _yolo_model, _plate_reader


def read_plate(reader, crop: Image.Image) -> str:
    """Read the plate from a crop; return the text, or "" when the reading is uncertain or does not look like a plate."""
    prediction = reader.run(np.array(crop.convert("RGB")), return_confidence=True)[0]
    text = re.sub(r"[^A-Z0-9]", "", (prediction.plate or "").upper())
    probs = prediction.char_probs
    if probs is None or len(probs) == 0 or float(np.min(probs)) < OCR_MIN_CONFIDENCE:
        return ""
    return text if is_valid_plate_format(text) else ""


def clean_plate_text(raw_text: str) -> str:
    """Clean the read text into the registration plate format."""
    if not raw_text:
        return ""
    # Uppercase letters and digits only
    cleaned = re.sub(r"[^A-Z0-9]", "", raw_text.upper())
    # OCR often reads the PL euroband as a 'PL', '1PL', 'IPL' etc. prefix
    for pfx in ("1PL", "IPL", "PL"):
        if cleaned.startswith(pfx) and len(cleaned) - len(pfx) >= 4:
            rem = cleaned[len(pfx):]
            if rem and rem[0].isalpha():
                cleaned = rem
                break
    return cleaned


def is_likely_dealer_badge(norm_text: str) -> bool:
    """Check whether the read text is dealer lettering such as OTOMOTO / KOMIS."""
    cleaned = re.sub(r"[^A-Z0-9]", "", (norm_text or "").upper())
    if cleaned in DEALER_WORDS:
        return True
    for dw in DEALER_WORDS:
        if len(dw) >= 4 and dw in cleaned:
            return True
    return False


def is_valid_plate_format(norm_text: str) -> bool:
    """Check whether length and structure look like a registration plate (PL: 4-8 characters, starting with a letter)."""
    cleaned = clean_plate_text(norm_text)
    if not cleaned or len(cleaned) < 4 or len(cleaned) > 8:
        return False
    if not cleaned[0].isalpha():
        return False
    has_letter = any(c.isalpha() for c in cleaned)
    has_digit = any(c.isdigit() for c in cleaned)
    return has_letter and has_digit


def process_image(img_pil: Image.Image, img_id_prefix: str) -> List[Dict]:
    """Detect plates in a PIL image, score the shot (straight front/rear view) and read the number."""
    model, reader = get_models()

    results = model(img_pil, conf=0.30, verbose=False)
    boxes = results[0].boxes
    candidates = []

    w, h = img_pil.size

    for i, b in enumerate(boxes):
        xyxy = b.xyxy[0].cpu().numpy().astype(int)
        conf = float(b.conf[0])

        bw = xyxy[2] - xyxy[0]
        bh = xyxy[3] - xyxy[1]
        if bw < 30 or bh < 8:
            continue

        # Score how straight-on the shot is (front / rear of the car)
        aspect_ratio = float(bw) / float(max(1, bh))
        ar_diff = abs(aspect_ratio - 4.56)

        aspect_score = max(0.0, 1.0 - (ar_diff / 2.2))
        area_score = min(1.0, float(bw * bh) / 14000.0)

        # Frame centre (straight front/rear photos usually have the plate in the middle)
        cx = (xyxy[0] + xyxy[2]) / (2.0 * max(1, w))
        center_score = 1.0 - min(1.0, abs(cx - 0.5) * 1.8)

        shot_quality_score = (aspect_score * 0.40) + (area_score * 0.25) + (center_score * 0.15) + (conf * 0.20)

        # Padding for the full crop shown in the UI
        pad_x = max(4, int(bw * 0.05))
        pad_y = max(4, int(bh * 0.06))

        x1 = max(0, xyxy[0] - pad_x)
        y1 = max(0, xyxy[1] - pad_y)
        x2 = min(w, xyxy[2] + pad_x)
        y2 = min(h, xyxy[3] + pad_y)

        full_crop = img_pil.crop((x1, y1, x2, y2))

        def candidate(plate_text: str) -> Dict:
            # Save the crop to a local file and build a base64 data URI
            crop_filename = f"crop_{img_id_prefix}_{i}.jpg"
            full_crop.save(os.path.join(CROPS_DIR, crop_filename), "JPEG", quality=85)
            buf = io.BytesIO()
            full_crop.save(buf, format="JPEG", quality=85)
            return {
                "detected_plate": plate_text,
                "confidence": round(conf, 3),
                "crop_path": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
                "bbox": [x1, y1, x2, y2],
                "aspect_ratio": round(aspect_ratio, 2),
                "shot_quality_score": round(shot_quality_score, 3),
                "is_standard_format": is_valid_plate_format(plate_text),
            }

        # Background check: a Polish plate has a light (white) background.
        crop_arr = np.array(full_crop)
        ch, cw = crop_arr.shape[:2]
        center_area = crop_arr[int(ch * 0.2):int(ch * 0.8), int(cw * 0.2):int(cw * 0.8)]
        if center_area.size > 0:
            mean_brightness = float(np.mean(center_area))
            if mean_brightness < 60:
                continue

        # An unreadable crop is kept without text: a human can often read it
        plate_text = read_plate(reader, full_crop)
        if plate_text and is_likely_dealer_badge(plate_text):
            continue
        candidates.append(candidate(plate_text))

    return candidates


_curl_session = None

def get_curl_session():
    global _curl_session
    if _curl_session is None:
        try:
            from curl_cffi import requests as cffi_requests
            _curl_session = cffi_requests.Session(impersonate="chrome124")
        except Exception:
            _curl_session = None
    return _curl_session


def download_image(url: str, timeout: int = 12) -> Optional[Image.Image]:
    """Download a photo from a URL and return it as a PIL image."""
    if not url:
        return None
    session = get_curl_session()
    if session:
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        print(f"    [download error] {url}: {e}")
        return None


def fetch_listing_gallery_photos(source_url: str) -> List[str]:
    """Fetch the full photo list of a listing (Otomoto __NEXT_DATA__ or OLX) when the DB has only 1 thumbnail."""
    if not source_url or not source_url.startswith("http"):
        return []
    html = ""
    session = get_curl_session()
    if session:
        try:
            resp = session.get(source_url, timeout=15)
            if resp.status_code == 200:
                html = resp.text
        except Exception as e:
            print(f"    [gallery fetch curl_cffi error] {source_url}: {e}")
    if not html:
        try:
            req = urllib.request.Request(
                source_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"    [gallery fetch error] {source_url}: {e}")
            return []

    if html:
        # Otomoto NEXT_DATA
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                advert = data.get("props", {}).get("pageProps", {}).get("advert", {})
                photos = advert.get("images", {}).get("photos", [])
                urls = []
                for p in photos:
                    u = p.get("id") or p.get("url") if isinstance(p, dict) else (p if isinstance(p, str) else None)
                    if u:
                        urls.append(u)
                if urls:
                    return urls
            except Exception:
                pass

        # OLX fallback / apollo cdn regex
        urls = re.findall(r'https://ireland\.apollo\.olxcdn\.com/v1/files/[a-zA-Z0-9_\-]+/image', html)
        if urls:
            seen = set()
            clean_urls = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    clean_urls.append(u)
            return clean_urls
    return []


def find_best_plate_shot(listing: dict, db_conn: sqlite3.Connection) -> Optional[Dict]:
    """Scan the listing photos and return the best plate shot (front/rear), or None."""
    lid = str(listing.get("id") or listing.get("source_listing_id") or "")
    vin = (listing.get("vin") or "").strip().upper()
    source_url = listing.get("source_url") or ""

    photos_raw = listing.get("photos")
    photo_urls = []
    if photos_raw:
        if isinstance(photos_raw, list):
            photo_urls = photos_raw
        elif isinstance(photos_raw, str):
            try:
                photo_urls = json.loads(photos_raw)
            except Exception:
                if photos_raw.startswith("http"):
                    photo_urls = [photos_raw]

    # With only 1 photo (or none) in the DB and a link to the listing,
    # fetch the whole gallery (up to a dozen or so photos) and update the DB
    if len(photo_urls) <= 1 and source_url:
        gallery = fetch_listing_gallery_photos(source_url)
        if gallery:
            photo_urls = gallery
            try:
                db_conn.execute("UPDATE pending_listings SET photos = ? WHERE id = ?", (json.dumps(gallery), lid))
                db_conn.commit()
                print(f"    [gallery fetched] Pobrano {len(gallery)} zdjęć z ogłoszenia dla ID: {lid}")
            except Exception:
                pass

    if not photo_urls:
        return None

    # Check up to 12 photos for the best shot (front / rear)
    photo_urls = photo_urls[:12]
    all_candidates = []

    for idx, purl in enumerate(photo_urls):
        img_id_prefix = f"{lid}_{idx}"
        img = download_image(purl)
        if img is None:
            continue

        cands = process_image(img, img_id_prefix)
        for c in cands:
            c["photo_url"] = purl
            all_candidates.append(c)

    if not all_candidates:
        return None

    # Best shot selection:
    # only candidates with a valid plate format (strictly 4 to 8 characters)
    valid_candidates = [
        c for c in all_candidates 
        if c.get("is_standard_format") and 4 <= len(re.sub(r"[^A-Z0-9]", "", c.get("detected_plate") or "")) <= 8
    ]

    if valid_candidates:
        valid_candidates.sort(
            key=lambda c: (c["shot_quality_score"], c["confidence"]),
            reverse=True
        )
        # Drop very poor shots (e.g. a cut-off bumper or an angle over 60 degrees)
        if valid_candidates[0]["shot_quality_score"] >= 0.28:
            return valid_candidates[0]
        print(f"    [skipped] Zbyt duży kąt zdjęcia dla {vin or lid} (score: {valid_candidates[0]['shot_quality_score']})")

    # Nothing reliable to read: return the best crop without text for a human to judge
    best_box = max(all_candidates, key=lambda c: (c["shot_quality_score"], c["confidence"]))
    return {**best_box, "detected_plate": ""}


def scan_listing_for_plates(listing: dict, db_conn: sqlite3.Connection) -> List[Dict]:
    """Scan the listing photos, find the best front/rear shot and save that candidate."""
    lid = str(listing.get("id") or listing.get("source_listing_id") or "")
    vin = (listing.get("vin") or "").strip().upper()
    status = (listing.get("status") or "").strip().lower()
    source_url = listing.get("source_url") or ""

    # Skip rejected listings and listings without a valid VIN
    if status == "rejected" or not vin or vin.startswith("PLH"):
        return []

    best_candidate = find_best_plate_shot(listing, db_conn)
    if not best_candidate:
        return []

    plate_text = best_candidate["detected_plate"]
    conf = best_candidate["confidence"]
    crop_path = best_candidate["crop_path"]
    purl = best_candidate["photo_url"]

    # Check whether this plate is already queued for this vehicle
    exists = db_conn.execute("""
        SELECT id FROM plate_review_queue 
        WHERE (vin = ? OR listing_id = ?) AND (REPLACE(detected_plate, ' ', '') = ? OR status = 'approved')
    """, (vin or "NONE", lid, plate_text)).fetchone()

    found_candidates = []
    if not exists:
        cur = db_conn.execute("""
            INSERT INTO plate_review_queue
            (listing_id, vin, source_url, photo_url, crop_path, detected_plate, confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (lid, vin or None, source_url, purl, crop_path, plate_text, conf))
        db_conn.commit()
        best_candidate["id"] = getattr(cur, "lastrowid", None)
        found_candidates.append(best_candidate)
        print(f"    [BEST SHOT SELECTED] {plate_text} (shot score: {best_candidate['shot_quality_score']}, conf: {conf:.2f}, AR: {best_candidate['aspect_ratio']})")

    return found_candidates


def fill_missing_crops(conn) -> Dict:
    """Scan photos for queue entries that have no crop.

    A plate from the listing text that CEPiK did not find is queued without a crop
    (requeue_for_plate_check), because the photo scan covers only listings without a plate.
    Here it gets a crop from the photos, and the reading from the photo becomes the proposal;
    the plate from the listing stays on the car, so the card still shows it. A crop without
    a reading leaves the proposal unchanged. An empty crop_path means nothing was found in
    the photos (not scanned again).
    """
    from webapp.services.plates import normalize_plate

    rows = conn.execute("""
        SELECT id, vin, detected_plate FROM plate_review_queue
        WHERE status = 'pending' AND crop_path IS NULL
          AND vin IS NOT NULL AND vin != '' AND vin NOT LIKE 'PLH%'
        ORDER BY id
    """).fetchall()
    print(f"\n[plate_scanner] {len(rows)} pozycji w kolejce bez wycinka...")

    filled = 0
    for q in rows:
        listing = conn.execute("""
            SELECT id, source_listing_id, vin, photos, source_url FROM pending_listings
            WHERE vin = ? AND photos IS NOT NULL AND photos NOT IN ('', '[]')
            ORDER BY id DESC LIMIT 1
        """, (q["vin"],)).fetchone()
        best = find_best_plate_shot(dict(listing), conn) if listing else None
        if not best:
            conn.execute("UPDATE plate_review_queue SET crop_path = '' WHERE id = ?", (q["id"],))
            conn.commit()
            print(f"  {q['vin']}: brak tablicy na zdjęciach")
            continue

        if not best["detected_plate"]:
            conn.execute("UPDATE plate_review_queue SET crop_path = ?, photo_url = ?, listing_id = COALESCE(listing_id, ?) WHERE id = ?",
                         (best["crop_path"], best["photo_url"], str(listing["id"]), q["id"]))
            conn.commit()
            filled += 1
            print(f"  {q['vin']}: wycinek bez odczytu")
            continue

        same = normalize_plate(best["detected_plate"]) == normalize_plate(q["detected_plate"])
        conn.execute("""
            UPDATE plate_review_queue
            SET crop_path = ?, photo_url = ?, listing_id = COALESCE(listing_id, ?),
                detected_plate = ?, confidence = ?
            WHERE id = ?
        """, (best["crop_path"], best["photo_url"], str(listing["id"]),
              best["detected_plate"], best["confidence"], q["id"]))
        conn.commit()
        filled += 1
        note = "zgodna z ogłoszeniem" if same else f"ogłoszenie: {q['detected_plate']}"
        print(f"  {q['vin']}: {best['detected_plate']} ({note})")

    return {"queued_without_crop": len(rows), "crops_filled": filled}


def run_plate_detection_batch(limit: int = 15, rescan_empty: bool = False) -> Dict:
    """Scan listings that have no registration plate."""
    try:
        from db import get_db
        conn = get_db()
    except Exception:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

    # Make sure the tables exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plate_review_queue (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id          TEXT,
            vin                 TEXT,
            source_url          TEXT,
            photo_url           TEXT,
            crop_path           TEXT,
            detected_plate      TEXT,
            confidence          REAL,
            status              TEXT NOT NULL DEFAULT 'pending',
            reviewed_plate      TEXT,
            reviewed_at         TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plate_scan_log (
            listing_id TEXT PRIMARY KEY,
            scanned_at TEXT DEFAULT (datetime('now')),
            plates_found INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    limit_clause = "LIMIT ?" if (limit and limit > 0) else ""
    params = (limit,) if (limit and limit > 0) else ()

    if not rescan_empty:
        scan_log_filter = "AND id NOT IN (SELECT CAST(listing_id AS INTEGER) FROM plate_scan_log)"
    else:
        scan_log_filter = "AND (id NOT IN (SELECT CAST(listing_id AS INTEGER) FROM plate_scan_log) OR id IN (SELECT CAST(listing_id AS INTEGER) FROM plate_scan_log WHERE plates_found = 0))"

    # Approved listings with a real VIN and photos, and no plate (neither on the listing nor on the
    # vehicle). A damaged car from the USA or Canada is still abroad: no Polish plate to find.
    from webapp.helpers import overseas_damaged_listing_sql
    overseas = overseas_damaged_listing_sql("pending_listings")
    rows = conn.execute(f"""
        SELECT id, source_listing_id, vin, photos, source_url, make, model, year
        FROM pending_listings
        WHERE (registration_plate IS NULL OR registration_plate = '')
          AND status = 'approved'
          AND vin IS NOT NULL
          AND vin != ''
          AND vin NOT LIKE 'PLH%'
          AND vin NOT LIKE 'UNVERIFIED%'
          AND vin NOT IN (SELECT vin FROM vehicles
                          WHERE registration_plate IS NOT NULL AND registration_plate != '')
          AND photos IS NOT NULL 
          AND photos != ''
          AND photos != '[]'
          AND NOT {overseas}
          {scan_log_filter}
        ORDER BY id DESC
        {limit_clause}
    """, params).fetchall()

    crops = fill_missing_crops(conn)

    print(f"\n[plate_scanner] Znaleziono {len(rows)} ogłoszeń do przeskanowania (rescan_empty={rescan_empty})...")

    total_scanned = 0
    total_found = 0

    for r in rows:
        item = dict(r)
        lid = item.get('id')
        print(f"  Skanuję {item.get('make')} {item.get('model')} ({item.get('vin') or 'Brak VIN'}, ID: {lid})...")
        cands = scan_listing_for_plates(item, conn)
        total_scanned += 1
        total_found += len(cands)
        try:
            conn.execute("INSERT OR REPLACE INTO plate_scan_log (listing_id, plates_found) VALUES (?, ?)", (str(lid), len(cands)))
            conn.commit()
        except Exception:
            pass

    conn.close()
    return {
        "scanned_count": total_scanned,
        "found_plates": total_found,
        **crops,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Lokalna detekcja tablic rejestracyjnych (YOLOv8 + fast-plate-ocr)")
    parser.add_argument("--limit", type=int, default=15, help="Limit ogłoszeń")
    parser.add_argument("--rescan-empty", action="store_true", help="Ponów próbę dla ogłoszeń bez tablicy (gdzie poprzednio było 0)")
    args = parser.parse_args()

    print(f"Uruchamiam detekcję tablic rejestracyjnych (limit: {args.limit}, rescan_empty: {args.rescan_empty})...")
    res = run_plate_detection_batch(limit=args.limit, rescan_empty=args.rescan_empty)
    print(f"\nZakończono! Przeskanowano {res['scanned_count']} aut, znaleziono {res['found_plates']} propozycji tablic.")
    print(f"Wycinki dla kolejki: {res['crops_filled']}/{res['queued_without_crop']}.")

    # A plate CEPiK confirms needs no review
    from scripts.fetch_cepik import confirm_queue_with_cepik
    confirm_queue_with_cepik()
