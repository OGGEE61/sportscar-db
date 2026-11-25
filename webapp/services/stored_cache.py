"""Aggregates kept in the database (app_cache), so a cold serverless instance does not recompute them.

Vercel starts fresh instances often, and an in-memory cache dies with them: the dashboard
recomputed its aggregates (~200k D1 rows read) on most visits, and the free plan allows 5 million
rows a day. A value stored here is read back with one row until it is older than its TTL.
"""
import json
import time

from flask import current_app

from db import get_db


def stored(key: str, ttl_s: int, compute):
    """compute()'s JSON-able value, kept in app_cache for ttl_s seconds (recomputed when older)."""
    if current_app and current_app.testing:
        return compute()
    conn = get_db()
    try:
        try:
            row = conn.execute("SELECT value, computed_at FROM app_cache WHERE key = ?", (key,)).fetchone()
        except Exception:      # table not migrated yet: no stored value
            row = None
        if row and time.time() - float(row["computed_at"]) < ttl_s:
            return json.loads(row["value"])
        value = compute()
        try:
            conn.execute("INSERT OR REPLACE INTO app_cache (key, value, computed_at) VALUES (?, ?, ?)",
                         (key, json.dumps(value), time.time()))
            conn.commit()
        except Exception:
            pass
        return value
    finally:
        conn.close()
