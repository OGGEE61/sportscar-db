"""How much of the D1 free plan the app has used, from Cloudflare's own analytics.

The free plan allows 5 million rows read a day (CLAUDE.md, "D1 read budget"). Asking the analytics
API costs no D1 reads. Needs CF_ANALYTICS_TOKEN (Account Analytics: Read) next to the CF_ACCOUNT_ID
and CF_D1_DATABASE_ID the app already has; without it every function here returns None and the
dashboard shows nothing. Nothing here prints the token or raises.
"""
import datetime
import os
import time

import requests

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
READS_PER_DAY = 5_000_000
CACHE_S = 600

_QUERY = """query($a: String!, $d: String!, $from: Date!, $to: Date!) {
  viewer { accounts(filter: {accountTag: $a}) {
    d1AnalyticsAdaptiveGroups(limit: 40, orderBy: [date_ASC],
        filter: {databaseId: $d, date_geq: $from, date_leq: $to}) {
      dimensions { date }
      sum { readQueries rowsRead rowsWritten }
    }
  } }
}"""

_cache = {"at": 0.0, "value": None}


def daily_usage(days: int = 10):
    """[{"date", "rows_read", "rows_written", "read_queries"}] for the last `days` days (UTC, oldest
    first; a day with no traffic is missing), or None when it cannot be read."""
    token = os.environ.get("CF_ANALYTICS_TOKEN")
    account, database = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_D1_DATABASE_ID")
    if not (token and account and database):
        return None
    today = datetime.datetime.now(datetime.timezone.utc).date()
    try:
        response = requests.post(
            GRAPHQL_URL, headers={"Authorization": f"Bearer {token}"}, timeout=5,
            json={"query": _QUERY, "variables": {
                "a": account, "d": database,
                "from": str(today - datetime.timedelta(days=days - 1)), "to": str(today)}})
        groups = response.json()["data"]["viewer"]["accounts"][0]["d1AnalyticsAdaptiveGroups"]
        return [{"date": g["dimensions"]["date"], "rows_read": g["sum"]["rowsRead"],
                 "rows_written": g["sum"]["rowsWritten"], "read_queries": g["sum"]["readQueries"]}
                for g in groups]
    except Exception as e:
        print(f"[d1 usage] not read: {type(e).__name__}", flush=True)
        return None


def rows_read_today():
    """Rows read so far today (UTC), kept for CACHE_S seconds; None when it cannot be read."""
    if time.time() - _cache["at"] < CACHE_S:
        return _cache["value"]
    usage = daily_usage(days=1)
    value = None
    if usage is not None:
        today = str(datetime.datetime.now(datetime.timezone.utc).date())
        value = sum(u["rows_read"] for u in usage if u["date"] == today)
    _cache.update(at=time.time(), value=value)
    return value
