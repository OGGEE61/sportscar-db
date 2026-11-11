"""Presigned GET links to photos in the R2 bucket, made while rendering a page.

Without R2_PUBLIC_URL every photo went through the /media route: one function invocation per
<img> (a page of cars is dozens of them), each importing boto3 and only then redirecting to R2.
On a phone they queued up, photos did not load and the next page waited behind them. Signing a
link is a local computation (AWS Signature V4, a few HMACs, no network), so pages now link
straight to R2.

The signing time is rounded down to SIGN_EVERY_S, so a photo keeps the same URL for that long and
the browser cache keeps working across pages and reloads; the link stays valid for EXPIRES_S from
the rounded time, at least EXPIRES_S - SIGN_EVERY_S after the page was rendered.
"""
import hashlib
import hmac
import os
import time
from typing import Optional
from urllib.parse import quote, urlsplit

SIGN_EVERY_S = 3600
EXPIRES_S = 4 * 3600
REGION = "auto"


def _settings() -> Optional[tuple]:
    env = os.environ
    keys = ("R2_ENDPOINT_URL", "R2_BUCKET_NAME", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    if not all(env.get(k) for k in keys):
        return None
    return tuple(env[k] for k in keys)


def configured() -> bool:
    return _settings() is not None


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def presigned_url(key: str, now: Optional[float] = None) -> Optional[str]:
    """A presigned GET URL for object `key` (path-style, like boto3 with an endpoint_url), or
    None when R2 is not configured."""
    settings = _settings()
    if not settings:
        return None
    endpoint, bucket, access_key, secret = settings
    signed_at = int(now if now is not None else time.time()) // SIGN_EVERY_S * SIGN_EVERY_S
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(signed_at))
    datestamp = amz_date[:8]
    scope = f"{datestamp}/{REGION}/s3/aws4_request"

    parts = urlsplit(endpoint.rstrip("/"))
    host = parts.netloc
    path = f"{parts.path}/{bucket}/{key.lstrip('/')}"
    canonical_uri = quote(path, safe="/~")
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(EXPIRES_S),
        "X-Amz-SignedHeaders": "host",
    }
    query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(params.items()))
    canonical_request = "\n".join(["GET", canonical_uri, query, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"])
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                hashlib.sha256(canonical_request.encode()).hexdigest()])
    signing_key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret}".encode(), datestamp), REGION), "s3"), "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{parts.scheme}://{host}{canonical_uri}?{query}&X-Amz-Signature={signature}"
