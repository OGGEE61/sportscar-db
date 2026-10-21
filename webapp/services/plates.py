"""Plate review queue helpers shared by the /plates API and the CEPiK sync."""
import json
import re


def normalize_plate(plate):
    return re.sub(r"[^A-Z0-9]", "", (plate or "").upper())


def clear_plate(conn, vin, listing_id, plate):
    """Remove `plate` from the listing, vehicle and observations (only where it matches)
    and mark the car as missing a plate."""
    if not plate:
        return
    if listing_id:
        conn.execute("UPDATE pending_listings SET registration_plate=NULL WHERE id=? AND registration_plate=?", (listing_id, plate))
    if not vin:
        return
    conn.execute("UPDATE pending_listings SET registration_plate=NULL WHERE vin=? AND registration_plate=?", (vin, plate))
    conn.execute("""
        UPDATE vehicles
        SET registration_plate=NULL,
            vin_status = CASE WHEN vin LIKE 'UNVERIFIED%' THEN 'placeholder' ELSE 'unverified' END
        WHERE vin=? AND registration_plate=?
    """, (vin, plate))
    conn.execute("UPDATE listing_observations SET registration_plate=NULL WHERE vin=? AND registration_plate=?", (vin, plate))
    try:
        conn.execute("DELETE FROM tags WHERE vin=? AND tag IN ('photo extracted', 'AI extracted plate')", (vin,))
        conn.execute("INSERT OR IGNORE INTO tags (vin, tag, source_method) VALUES (?, 'missing plates', 'system')", (vin,))
    except Exception:
        pass


def requeue_for_plate_check(conn, vin, plate):
    """CEPiK did not find this VIN + plate: send the plate back to /plates for a human check.

    A plate read from a photo goes back to 'pending' and is cleared from the car (like Revert).
    A plate that came from the listing text has no queue entry, so one is created and the
    plate stays on the car until the reviewer corrects it.
    Returns "already_pending", "reverted" or "queued".
    """
    if conn.execute("SELECT 1 FROM plate_review_queue WHERE vin=? AND status='pending'", (vin,)).fetchone():
        return "already_pending"

    for cand in conn.execute(
            "SELECT * FROM plate_review_queue WHERE vin=? AND status='approved' ORDER BY id DESC", (vin,)).fetchall():
        if normalize_plate(cand["reviewed_plate"]) == normalize_plate(plate):
            conn.execute("UPDATE plate_review_queue SET status='pending', reviewed_plate=NULL, reviewed_at=NULL WHERE id=?",
                         (cand["id"],))
            clear_plate(conn, vin, cand["listing_id"], cand["reviewed_plate"])
            conn.commit()
            return "reverted"

    photo_url = None
    row = conn.execute("SELECT photos FROM pending_listings WHERE vin=? AND photos IS NOT NULL AND photos NOT IN ('', '[]') "
                       "ORDER BY id DESC LIMIT 1", (vin,)).fetchone()
    if row:
        try:
            photos = json.loads(row["photos"])
            photo_url = photos[0] if photos else None
        except (ValueError, TypeError):
            pass
    obs = conn.execute("SELECT source_url FROM listing_observations WHERE vin=? ORDER BY observed_at DESC, id DESC LIMIT 1",
                       (vin,)).fetchone()
    conn.execute("""INSERT INTO plate_review_queue (vin, source_url, photo_url, detected_plate, confidence, status)
                    VALUES (?, ?, ?, ?, 0, 'pending')""", (vin, obs["source_url"] if obs else None, photo_url, plate))
    conn.commit()
    return "queued"


def allow_cepik_retry(conn, vin, plate):
    """A reviewed plate that differs from the one CEPiK rejected deserves a new lookup
    (the sync skips cars logged as not_found; the log message names the rejected plate)."""
    try:
        conn.execute("DELETE FROM cepik_sync_log WHERE vin=? AND status='not_found' AND message NOT LIKE ?",
                     (vin, f"%tablica {normalize_plate(plate)}%"))
    except Exception:
        pass  # cepik_sync_log not created yet
