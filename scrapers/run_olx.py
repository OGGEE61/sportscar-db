"""Run OLX scrapers.

Usage:
    python scrapers/run_olx.py              # runs all OLX models
    python scrapers/run_olx.py all          # runs all OLX models
    python scrapers/run_olx.py alpina       # runs only BMW Alpina OLX scraper
"""
import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "olx"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

from base_scraper import run, _log_run
from bmw_alpina import CONFIG as ALPINA_OLX

ALL_OLX_FLEET = [
    ALPINA_OLX,
]

SCRAPER_MAP = {
    "alpina": [ALPINA_OLX],
    "all": ALL_OLX_FLEET,
}

if __name__ == "__main__":
    target = os.getenv("SCRAPER_TARGET")
    if not target and len(sys.argv) > 1:
        target = sys.argv[1].lower()
    if not target:
        target = "all"

    scrapers_to_run = SCRAPER_MAP.get(target, ALL_OLX_FLEET)
    print(f"Running OLX scraper target: {target} ({len(scrapers_to_run)} scraper(s))")

    totals = {"total": 0, "new": 0, "duplicate": 0}
    for i, cfg in enumerate(scrapers_to_run):
        print(f"\n--- [{i+1}/{len(scrapers_to_run)}] {cfg.make} {cfg.model} (OLX) ---")
        try:
            results = run(cfg, post_to_api=True)
            totals["total"] += len(results)
        except Exception as e:
            print(f"Error running {cfg.make} {cfg.model}: {e}")
        if (i + 1) < len(scrapers_to_run):
            time.sleep(random.uniform(2, 5))

    print(f"\nALL OLX DONE — {totals['total']} listings processed.")
