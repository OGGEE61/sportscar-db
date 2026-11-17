"""Rows D1 read and wrote per day, for the last N days (default 10), from Cloudflare's analytics.

    python scripts/maintenance/d1_usage.py [days]

Costs no D1 reads. Needs CF_ANALYTICS_TOKEN in .env (see README). The free plan allows 5 million
rows read a day; past that the app returns 500s until midnight UTC (01:00 Polish time).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()

from webapp.services.d1_usage import READS_PER_DAY, daily_usage


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    usage = daily_usage(days)
    if usage is None:
        print("Brak danych: ustaw CF_ANALYTICS_TOKEN, CF_ACCOUNT_ID i CF_D1_DATABASE_ID w .env.")
        return 1
    print("data         odczytane wiersze  % limitu   zapytania   zapisane wiersze")
    for u in usage:
        share = 100 * u["rows_read"] / READS_PER_DAY
        print(f'{u["date"]}  {u["rows_read"]:>17,}  {share:>7.1f}%  {u["read_queries"]:>10,}  {u["rows_written"]:>16,}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
