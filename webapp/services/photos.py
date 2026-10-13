import io
import os

from db import get_db
from webapp.helpers import PHOTOS_DIR
_LAST_STORAGE_CHECK = 0.0
_STORAGE_OK_CACHE = True

def check_storage_limit(conn) -> bool:
    """Returns True if we're under the estimated 7.5GB limit (cached for 6 hours)."""
    global _LAST_STORAGE_CHECK, _STORAGE_OK_CACHE
    import time
    now = time.time()
    if now - _LAST_STORAGE_CHECK < 21600:  # 6 hours cache
        return _STORAGE_OK_CACHE

    try:
        c1 = conn.execute("SELECT COUNT(local_photo) FROM pending_listings WHERE local_photo IS NOT NULL").fetchone()[0]
        c2 = conn.execute("SELECT COUNT(photo) FROM vehicles WHERE photo IS NOT NULL AND photo != ''").fetchone()[0]
        total_photos = c1 + c2
        # Estimate 20KB per photo (400px, 60% quality)
        estimated_gb = (total_photos * 20.0) / 1024 / 1024
        _STORAGE_OK_CACHE = (estimated_gb < 7.5)
        _LAST_STORAGE_CHECK = now
        return _STORAGE_OK_CACHE
    except Exception:
        return True

def save_photo(url: str, filename: str, max_width: int = 400, quality: int = 60):
    """Download url, compress to JPEG, save to Cloudflare R2 (or local fallback)."""
    if not url:
        return None
        
    conn = get_db()
    under_limit = check_storage_limit(conn)
    conn.close()
    if not under_limit:
        print("Storage limit of 7.5GB exceeded, skipping photo upload.")
        return None

    try:
        from PIL import Image
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, timeout=12, impersonate="chrome")
        if resp.status_code != 200:
            return None
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
            
        endpoint = os.environ.get("R2_ENDPOINT_URL")
        bucket = os.environ.get("R2_BUCKET_NAME")
        
        if endpoint and bucket:
            import boto3
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=quality, optimize=True)
            buffer.seek(0)
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
                region_name="auto"
            )
            s3.upload_fileobj(buffer, bucket, f"photos/{filename}", ExtraArgs={'ContentType': 'image/jpeg'})
            return f"photos/{filename}"
        else:
            path = os.path.join(PHOTOS_DIR, filename)
            img.save(path, "JPEG", quality=quality, optimize=True)
            return f"photos/{filename}"
    except Exception as e:
        print(f"Error saving photo: {e}")
        return None
