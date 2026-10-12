"""Lokalny moduł detekcji tablic rejestracyjnych (YOLOv8 + EasyOCR).

Wyszukuje tablice rejestracyjne na zdjęciach samochodów, wycina zbliżenie
i odczytuje numer, a następnie zapisuje propozycje do kolejki weryfikacji
Human-in-the-Loop (`plate_review_queue`).
"""

import os
import re
import io
import json
import base64
import sqlite3
import urllib.request
from typing import List, Dict, Optional, Tuple
from PIL import Image, ImageEnhance
import numpy as np

# Silniki CV & OCR
from ultralytics import YOLO
import easyocr

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

# Słowa-klucze na ramkach tablic lub tablicach komisowych / reklamowych do odfiltrowania
DEALER_WORDS = {
    "OTOMOTO", "OLX", "KOMIS", "SALON", "AUTOPLUS", "VIP", "CAR",
    "DEALER", "SERVICE", "BMW", "AUDI", "MERCEDES", "PORSCHE", "AUTA",
    "POZNAN", "WARSZAWA", "KRAKOW", "WROCLAW", "GDANSK", "POLSKA", "PL"
}

_yolo_model = None
_easyocr_reader = None


def get_models():
    """Lazy loader dla modeli, aby nie obciążać pamięci przy samym imporcie."""
    global _yolo_model, _easyocr_reader
    if _yolo_model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Brak pliku wag modelu: {MODEL_PATH}")
        _yolo_model = YOLO(MODEL_PATH)
    if _easyocr_reader is None:
        # Alfabet łaciński / cyfry
        _easyocr_reader = easyocr.Reader(["en"], gpu=False)
    return _yolo_model, _easyocr_reader


def clean_plate_text(raw_text: str) -> str:
    """Czyści odczytany ciąg znaków do standardu tablicy rejestracyjnej."""
    if not raw_text:
        return ""
    # Tylko wielkie litery i cyfry
    cleaned = re.sub(r"[^A-Z0-9]", "", raw_text.upper())
    # Euroband z flagą PL często jest czytany przez OCR jako prefiks 'PL'
    if cleaned.startswith("PL") and len(cleaned) >= 7:
        cleaned = cleaned[2:]
    return cleaned


def is_likely_dealer_badge(norm_text: str) -> bool:
    """Sprawdza, czy odczytany tekst to napis reklamowy typu OTOMOTO / KOMIS."""
    if norm_text in DEALER_WORDS:
        return True
    for dw in DEALER_WORDS:
        if len(dw) >= 4 and dw in norm_text:
            return True
    return False


def is_valid_plate_format(norm_text: str) -> bool:
    """Sprawdza, czy długość i struktura przypomina tablicę rejestracyjną (PL: 4-8 znaków)."""
    if not norm_text or len(norm_text) < 4 or len(norm_text) > 8:
        return False
    # Musi zawierać przynajmniej jedną literę i przynajmniej jedną cyfrę (lub być tablicą zabytkową/indywidualną)
    has_letter = any(c.isalpha() for c in norm_text)
    has_digit = any(c.isdigit() for c in norm_text)
    return has_letter and has_digit


def process_image(img_pil: Image.Image, img_id_prefix: str) -> List[Dict]:
    """Wykrywa tablice na pojedynczym obrazie PIL i zwraca znalezionych kandydatów."""
    model, reader = get_models()

    results = model(img_pil, conf=0.30, verbose=False)
    boxes = results[0].boxes
    candidates = []

    w, h = img_pil.size

    for i, b in enumerate(boxes):
        xyxy = b.xyxy[0].cpu().numpy().astype(int)
        conf = float(b.conf[0])

        # Dodaj delikatny margines (5% szerokości/wysokości) dla lepszego OCR
        bw = xyxy[2] - xyxy[0]
        bh = xyxy[3] - xyxy[1]
        pad_x = max(4, int(bw * 0.05))
        pad_y = max(4, int(bh * 0.08))

        x1 = max(0, xyxy[0] - pad_x)
        y1 = max(0, xyxy[1] - pad_y)
        x2 = min(w, xyxy[2] + pad_x)
        y2 = min(h, xyxy[3] + pad_y)

        crop = img_pil.crop((x1, y1, x2, y2))

        # Powiększ mały crop do min 200px wysokości dla lepszego OCR
        cw, ch = crop.size
        if ch < 120 and ch > 0:
            scale = 120.0 / ch
            crop = crop.resize((int(cw * scale), 120), Image.Resampling.LANCZOS)

        # Zwiększ kontrast dla OCR
        enhancer = ImageEnhance.Contrast(crop)
        enhanced_crop = enhancer.enhance(1.4)

        crop_np = np.array(enhanced_crop)
        ocr_results = reader.readtext(crop_np)

        raw_parts = [r[1] for r in ocr_results]
        joined = " ".join(raw_parts)
        norm_text = clean_plate_text(joined)

        # Odrzuć napisy komisowe / reklamowe
        if is_likely_dealer_badge(norm_text):
            continue

        if not norm_text or len(norm_text) < 4:
            continue

        # Zapisz wycięty fragment do pliku lokalnego oraz wygeneruj base64 data URI (aby działało na Vercelu i w chmurze)
        crop_filename = f"crop_{img_id_prefix}_{i}.jpg"
        crop_save_path = os.path.join(CROPS_DIR, crop_filename)
        crop.save(crop_save_path, "JPEG", quality=85)

        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=85)
        crop_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

        candidates.append({
            "detected_plate": norm_text,
            "raw_text": joined,
            "confidence": round(conf, 3),
            "crop_path": crop_b64,
            "bbox": [x1, y1, x2, y2],
            "is_standard_format": is_valid_plate_format(norm_text),
        })

    # Posortuj kandydatów: w pierwszej kolejności pasujące do formatu tablicy i z najwyższą pewnością
    candidates.sort(key=lambda c: (c["is_standard_format"], c["confidence"]), reverse=True)
    return candidates


def download_image(url: str, timeout: int = 10) -> Optional[Image.Image]:
    """Pobiera zdjęcie z adresu URL i zwraca obiekt PIL."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                )
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        print(f"    [download error] {url}: {e}")
        return None


def scan_listing_for_plates(listing: dict, db_conn: sqlite3.Connection) -> List[Dict]:
    """Skanuje zdjęcia danego ogłoszenia i zapisuje wykryte tablice do kolejki review."""
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

    if not photo_urls:
        return []

    # Ogranicz do pierwszych 8 zdjęć
    photo_urls = photo_urls[:8]
    found_candidates = []

    for idx, purl in enumerate(photo_urls):
        img_id_prefix = f"{lid}_{idx}"
        img = download_image(purl)
        if img is None:
            continue

        cands = process_image(img, img_id_prefix)
        for c in cands:
            plate_text = c["detected_plate"]
            conf = c["confidence"]
            crop_path = c["crop_path"]

            # Sprawdź, czy ta propozycja już istnieje w kolejce
            exists = db_conn.execute("""
                SELECT id FROM plate_review_queue 
                WHERE (vin = ? OR listing_id = ?) AND detected_plate = ?
            """, (vin or "NONE", lid, plate_text)).fetchone()

            if not exists:
                cur = db_conn.execute("""
                    INSERT INTO plate_review_queue
                    (listing_id, vin, source_url, photo_url, crop_path, detected_plate, confidence, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (lid, vin or None, source_url, purl, crop_path, plate_text, conf))
                db_conn.commit()
                c["id"] = getattr(cur, "lastrowid", None)
                found_candidates.append(c)
                print(f"    [plate found] {plate_text} (conf: {conf:.2f}) -> {crop_path}")

    return found_candidates


def run_plate_detection_batch(limit: int = 15) -> Dict:
    """Skanuje ogłoszenia bez numeru rejestracyjnego."""
    try:
        from db import get_db
        conn = get_db()
    except Exception:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

    # Upewnij się, że tabela istnieje
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
    conn.commit()

    # Pobierz ogłoszenia bez tablicy, które mają zdjęcia
    rows = conn.execute("""
        SELECT id, source_listing_id, vin, photos, source_url, make, model, year
        FROM pending_listings
        WHERE (registration_plate IS NULL OR registration_plate = '')
          AND photos IS NOT NULL 
          AND photos != ''
          AND photos != '[]'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    print(f"\n[plate_scanner] Znaleziono {len(rows)} ogłoszeń do przeskanowania...")

    total_scanned = 0
    total_found = 0

    for r in rows:
        item = dict(r)
        print(f"  Skanuję {item.get('make')} {item.get('model')} ({item.get('vin') or 'Brak VIN'}, ID: {item.get('id')})...")
        cands = scan_listing_for_plates(item, conn)
        total_scanned += 1
        total_found += len(cands)

    conn.close()
    return {
        "scanned_count": total_scanned,
        "found_plates": total_found
    }


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"Uruchamiam detekcję tablic rejestracyjnych (limit: {limit})...")
    res = run_plate_detection_batch(limit=limit)
    print(f"\nZakończono! Przeskanowano {res['scanned_count']} aut, znaleziono {res['found_plates']} propozycji tablic.")
