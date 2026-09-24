"""Run all scrapers in sequence.

Usage:
    python scrapers/run_all.py

The Flask app must be running first (python app.py).
Results are auto-approved when the VIN decrypts cleanly — no manual review
needed for those. Listings without a valid VIN land in /review as before.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

from base_scraper import run

from audi_rs3_8v        import CONFIG    as RS3
from audi_rs4_b85       import CONFIG    as RS4_B85
from audi_rs4_b9        import CONFIG    as RS4_B9
from bmw_m4_f82         import CONFIG_M4 as M4, CONFIG_M3 as M3
from mercedes_c63_w204  import CONFIG    as C63
from mercedes_e55_w211  import CONFIG    as E55

SCRAPERS = [RS4_B85, RS4_B9] # [RS3, RS4_B85, RS4_B9, M4, M3, C63, E55]

if __name__ == "__main__":
    totals = {"auto_approved": 0, "pending": 0, "duplicate": 0,
              "price_updated": 0, "total": 0}

    for cfg in SCRAPERS:
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        results = run(cfg)
        totals["total"] += len(results)
        time.sleep(2)   # brief pause between scrapers

    print(f"\n{'='*60}")
    print(f"  ALL DONE — {totals['total']} listings processed across {len(SCRAPERS)} scrapers")
    print(f"{'='*60}")
