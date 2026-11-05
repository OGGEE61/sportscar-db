"""Re-read pending review cards from their stored crops with the current plate reader.

A confident reading becomes the card's proposal. An unsure one blanks an old photo reading, so
it isn't approved by accident, and leaves a number from the listing as it is.

Usage: python scripts/maintenance/reread_queue_plates.py [--dry-run] [--yes]
Writes to the backend selected by DB_BACKEND (d1 = production) after confirmation.
"""
import base64
import io
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
from PIL import Image
import db
from scripts.detect_plates import get_models, is_likely_dealer_badge, read_plate
from webapp.services.plates import normalize_plate


def main():
    conn = db.get_db()
    cards = conn.execute("""
        SELECT id, crop_path, detected_plate, confidence FROM plate_review_queue
        WHERE status = 'pending' AND crop_path LIKE 'data:image%'
    """).fetchall()
    _, reader = get_models()

    updates = []
    outcome = Counter()
    for c in cards:
        crop = Image.open(io.BytesIO(base64.b64decode(c["crop_path"].split(",", 1)[1])))
        text = read_plate(reader, crop)
        if is_likely_dealer_badge(text):
            text = ""
        from_photo = (c["confidence"] or 0) > 0
        if text == normalize_plate(c["detected_plate"]):
            outcome["same reading"] += 1
        elif text:
            outcome["new reading"] += 1
            updates.append((text, c["confidence"] if from_photo else 0.7, c["id"]))
        elif from_photo and c["detected_plate"]:
            outcome["unsure: photo reading blanked"] += 1
            updates.append(("", c["confidence"], c["id"]))
        else:
            outcome["unsure: left as is"] += 1
    print(f"{len(cards)} pending card(s) with a crop")
    for name, n in outcome.most_common():
        print(f"  {n:5d}  {name}")
    if "--dry-run" in sys.argv or not updates:
        conn.close()
        return

    backend = os.environ.get("DB_BACKEND", "sqlite").lower()
    target = "PRODUCTION (Cloudflare D1)" if backend == "d1" else f"local SQLite ({db.DB_PATH})"
    if "--yes" not in sys.argv:
        if not sys.stdin.isatty():
            sys.exit(f"Refusing to write to {target} non-interactively; pass --yes to confirm.")
        if input(f"Update {len(updates)} card(s) in {target}? Type 'yes': ").strip() != "yes":
            sys.exit("Aborted, nothing changed.")
    for text, confidence, card_id in updates:
        conn.execute("UPDATE plate_review_queue SET detected_plate = ?, confidence = ? WHERE id = ?", (text, confidence, card_id))
    conn.commit()
    conn.close()
    print(f"Updated {len(updates)} card(s)")


if __name__ == "__main__":
    main()
