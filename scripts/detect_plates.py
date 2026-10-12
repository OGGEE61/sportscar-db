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


def format_polish_plate(raw_text: str) -> str:
    """Formatuje standardową polską tablicę: rozdziela wyróżnik powiatu spacją (np. OKR 9MM6, KR 7VG22)."""
    cleaned = clean_plate_text(raw_text)
    if not cleaned:
        return ""
    if 4 <= len(cleaned) <= 8:
        if len(cleaned) >= 5 and cleaned[:2].isalpha() and not cleaned[2].isalpha():
            return f"{cleaned[:2]} {cleaned[2:]}"
        elif len(cleaned) >= 6 and cleaned[:3].isalpha() and not cleaned[3].isalpha():
            return f"{cleaned[:3]} {cleaned[3:]}"
    return cleaned


def is_likely_dealer_badge(norm_text: str) -> bool:
    """Sprawdza, czy odczytany tekst to napis reklamowy typu OTOMOTO / KOMIS."""
    cleaned = re.sub(r"[^A-Z0-9]", "", (norm_text or "").upper())
    if cleaned in DEALER_WORDS:
        return True
    for dw in DEALER_WORDS:
        if len(dw) >= 4 and dw in cleaned:
            return True
    return False


def is_valid_plate_format(norm_text: str) -> bool:
    """Sprawdza, czy długość i struktura przypomina tablicę rejestracyjną (PL: 4-8 znaków)."""
    cleaned = re.sub(r"[^A-Z0-9]", "", (norm_text or "").upper())
    if not cleaned or len(cleaned) < 4 or len(cleaned) > 8:
        return False
    has_letter = any(c.isalpha() for c in cleaned)
    has_digit = any(c.isdigit() for c in cleaned)
    return has_letter and has_digit


def process_image(img_pil: Image.Image, img_id_prefix: str) -> List[Dict]:
    """Wykrywa tablice na obrazie PIL, ocenia jakość ujęcia (prostoliniowość przód/tył) i uruchamia zaawansowany OCR."""
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

        # Ocena ujęcia pod kątem prostoliniowości (przód / tył pojazdu)
        # Standardowa tablica UE ma stosunek boków 520x114 mm (~4.56 : 1)
        aspect_ratio = float(bw) / float(max(1, bh))
        ar_diff = abs(aspect_ratio - 4.56)

        # Ujęcia pod dużym kątem (3/4) mają aspect_ratio < 3.2 lub > 5.5
        aspect_score = max(0.0, 1.0 - (ar_diff / 2.2))
        area_score = min(1.0, float(bw * bh) / 14000.0)

        # Środek kadru (zdjęcia prostopadłe przód/tył zwykle mają tablicę w centrum)
        cx = (xyxy[0] + xyxy[2]) / (2.0 * max(1, w))
        center_score = 1.0 - min(1.0, abs(cx - 0.5) * 1.8)

        shot_quality_score = (aspect_score * 0.40) + (area_score * 0.25) + (center_score * 0.15) + (conf * 0.20)

        # Marginesy dla pełnego cropa do UI
        pad_x = max(4, int(bw * 0.05))
        pad_y = max(4, int(bh * 0.06))

        x1 = max(0, xyxy[0] - pad_x)
        y1 = max(0, xyxy[1] - pad_y)
        x2 = min(w, xyxy[2] + pad_x)
        y2 = min(h, xyxy[3] + pad_y)

        full_crop = img_pil.crop((x1, y1, x2, y2))

        # Weryfikacja tła: polska tablica musi mieć jasne (białe) tło.
        # Sprawdzamy średnią jasność i odrzucamy czarne elementy (grille, wloty, zderzaki)
        crop_arr = np.array(full_crop)
        ch, cw = crop_arr.shape[:2]
        center_area = crop_arr[int(ch * 0.2):int(ch * 0.8), int(cw * 0.2):int(cw * 0.8)]
        if center_area.size > 0:
            mean_brightness = float(np.mean(center_area))
            # Ciemne kratki chłodnicy lub czarny lakier mają jasność < 65
            if mean_brightness < 60:
                continue

        # Przygotowanie wycinka pod OCR:
        # 1. Odetnij dolne 16% ramki reklamowej (telefony, adresy www dealerów)
        ocr_bh = max(10, int(bh * 0.84))
        
        # 2. Dla poziomych tablic unijnych (AR > 3.0) odetnij lewy niebieski pasek (Euroband ~11% szerokości),
        # aby EasyOCR nie mylił gwiazdek UE i flagi z literami 'PL', '1', 'I', '['.
        ocr_x1 = xyxy[0]
        if aspect_ratio >= 3.0:
            ocr_x1 = xyxy[0] + max(4, int(bw * 0.11))

        ocr_crop = img_pil.crop((ocr_x1, xyxy[1], xyxy[2], xyxy[1] + ocr_bh))

        # Skaluj do znormalizowanej wysokości 70px
        scale = 70.0 / float(max(1, ocr_crop.size[1]))
        ocr_scaled = ocr_crop.resize((int(ocr_crop.size[0] * scale), 70), Image.Resampling.LANCZOS)

        # Zwiększ kontrast
        enhancer = ImageEnhance.Contrast(ocr_scaled)
        enhanced_crop = enhancer.enhance(1.4)

        crop_np = np.array(enhanced_crop)
        ocr_results = reader.readtext(crop_np, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

        if not ocr_results:
            continue

        # Wybierz najlepszy fragment z OCR pasujący do tablicy
        ocr_texts = []
        for r in ocr_results:
            t = r[1]
            c = r[2] if len(r) > 2 else 0.5
            ocr_texts.append((t, c))

        # Spróbuj złożyć lub wybrać główny blok
        joined = " ".join([t[0] for t in ocr_texts])
        norm_text = clean_plate_text(joined)

        # Polska tablica rejestracyjna ma ściśle od 4 do 8 znaków alfanumerycznych.
        # Jeśli połączony tekst ma > 8 znaków lub nie pasuje do wzorca, sprawdź pojedyncze bloki OCR
        if len(norm_text) > 8 or is_likely_dealer_badge(norm_text) or not is_valid_plate_format(norm_text):
            best_part = ""
            for t, _ in ocr_texts:
                cleaned_part = clean_plate_text(t)
                if is_valid_plate_format(cleaned_part) and not is_likely_dealer_badge(cleaned_part):
                    best_part = cleaned_part
                    break
            norm_text = best_part

        # Rygorystyczny warunek: jeśli tekst nadal ma >8 lub <4 znaki, ODRZUĆ go bezwzględnie!
        if not norm_text or len(norm_text) < 4 or len(norm_text) > 8 or not is_valid_plate_format(norm_text):
            continue

        formatted_plate = format_polish_plate(norm_text)

        # Zapisz wycięty fragment do pliku lokalnego oraz wygeneruj base64 data URI
        crop_filename = f"crop_{img_id_prefix}_{i}.jpg"
        crop_save_path = os.path.join(CROPS_DIR, crop_filename)
        full_crop.save(crop_save_path, "JPEG", quality=85)

        buf = io.BytesIO()
        full_crop.save(buf, format="JPEG", quality=85)
        crop_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

        candidates.append({
            "detected_plate": formatted_plate,
            "raw_text": joined,
            "confidence": round(conf, 3),
            "crop_path": crop_b64,
            "bbox": [x1, y1, x2, y2],
            "aspect_ratio": round(aspect_ratio, 2),
            "shot_quality_score": round(shot_quality_score, 3),
            "is_standard_format": is_valid_plate_format(norm_text),
        })

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


def fetch_listing_gallery_photos(source_url: str) -> List[str]:
    """Pobiera pełną listę zdjęć z ogłoszenia (np. z Otomoto __NEXT_DATA__ lub OLX), gdy w bazie jest tylko 1 miniatura."""
    if not source_url or not source_url.startswith("http"):
        return []
    try:
        req = urllib.request.Request(
            source_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                )
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Otomoto NEXT_DATA
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
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
    except Exception as e:
        print(f"    [gallery fetch error] {source_url}: {e}")
    return []


def scan_listing_for_plates(listing: dict, db_conn: sqlite3.Connection) -> List[Dict]:
    """Skanuje zdjęcia ogłoszenia, znajduje najlepsze ujęcie przód/tył i zapisuje optymalnego kandydata."""
    lid = str(listing.get("id") or listing.get("source_listing_id") or "")
    vin = (listing.get("vin") or "").strip().upper()
    status = (listing.get("status") or "").strip().lower()
    source_url = listing.get("source_url") or ""

    # Ignoruj ogłoszenia odrzucone lub bez prawidłowego VIN
    if status == "rejected" or not vin or vin.startswith("PLH"):
        return []

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

    # Jeśli w bazie mamy tylko 1 zdjęcie (lub brak), a mamy link do ogłoszenia,
    # dynamicznie pobieramy całą galerię (do kilkunastu zdjęć) i aktualizujemy bazę!
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
        return []

    # Sprawdź do 12 zdjęć w poszukiwaniu najlepszego ujęcia (przód / tył)
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
        return []

    # Inteligentny wybór najlepszego zdjęcia (Best Shot Selection):
    # Dopuszczamy TYLKO kandydatów o prawidłowym formacie tablicy (ściśle 4 do 8 znaków)
    valid_candidates = [
        c for c in all_candidates 
        if c.get("is_standard_format") and 4 <= len(re.sub(r"[^A-Z0-9]", "", c.get("detected_plate") or "")) <= 8
    ]

    if not valid_candidates:
        return []

    valid_candidates.sort(
        key=lambda c: (c["shot_quality_score"], c["confidence"]),
        reverse=True
    )

    best_candidate = valid_candidates[0]

    # Odrzuć ujęcia o skrajnie niskiej jakości (np. ucięty zderzak lub kąt > 60 stopni)
    if best_candidate["shot_quality_score"] < 0.28:
        print(f"    [skipped] Zbyt duży kąt zdjęcia dla {vin or lid} (score: {best_candidate['shot_quality_score']})")
        return []

    plate_text = best_candidate["detected_plate"]
    conf = best_candidate["confidence"]
    crop_path = best_candidate["crop_path"]
    purl = best_candidate["photo_url"]

    # Sprawdź, czy ta tablica już istnieje w kolejce dla tego pojazdu
    exists = db_conn.execute("""
        SELECT id FROM plate_review_queue 
        WHERE (vin = ? OR listing_id = ?) AND (detected_plate = ? OR status = 'approved')
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

    # Pobierz ogłoszenia bez tablicy, które mają zdjęcia, NIE są odrzucone, mają prawdziwy VIN i nie były jeszcze skanowane
    rows = conn.execute(f"""
        SELECT id, source_listing_id, vin, photos, source_url, make, model, year
        FROM pending_listings
        WHERE (registration_plate IS NULL OR registration_plate = '')
          AND status != 'rejected'
          AND vin IS NOT NULL 
          AND vin != '' 
          AND vin NOT LIKE 'PLH%'
          AND photos IS NOT NULL 
          AND photos != ''
          AND photos != '[]'
          AND id NOT IN (SELECT CAST(listing_id AS INTEGER) FROM plate_scan_log)
        ORDER BY id DESC
        {limit_clause}
    """, params).fetchall()

    print(f"\n[plate_scanner] Znaleziono {len(rows)} ogłoszeń do przeskanowania...")

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
        "found_plates": total_found
    }


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print(f"Uruchamiam detekcję tablic rejestracyjnych (limit: {limit})...")
    res = run_plate_detection_batch(limit=limit)
    print(f"\nZakończono! Przeskanowano {res['scanned_count']} aut, znaleziono {res['found_plates']} propozycji tablic.")
