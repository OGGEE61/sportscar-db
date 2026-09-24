"""Run scrapers in sequence or selectively.

Usage:
    python scrapers/run_all.py              # runs all active fleet scrapers
    python scrapers/run_all.py c63          # runs only C63 W204
    python scrapers/run_all.py e55          # runs only E55 W211
    python scrapers/run_all.py rs4_b85      # runs only RS4 B8.5 Avant
    python scrapers/run_all.py rs4_b9       # runs only RS4 B9 Avant
    python scrapers/run_all.py rs4          # runs both RS4 scrapers
    python scrapers/run_all.py all          # runs all active fleet scrapers
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

# Active target fleet
DEFAULT_FLEET = [C63, E55, RS4_B85, RS4_B9]

SCRAPER_MAP = {
    "c63": [C63],
    "e55": [E55],
    "rs4_b85": [RS4_B85],
    "rs4_b9": [RS4_B9],
    "rs4": [RS4_B85, RS4_B9],
    "rs3": [RS3],
    "m3": [M3],
    "m4": [M4],
    "fleet": DEFAULT_FLEET,
    "all": DEFAULT_FLEET,
}

if __name__ == "__main__":
    target = os.environ.get("SCRAPER_TARGET", "").lower().strip()
    if len(sys.argv) > 1:
        target = sys.argv[1].lower().strip()

    if target and target in SCRAPER_MAP:
        scrapers_to_run = SCRAPER_MAP[target]
        print(f"Target selected: {target} ({len(scrapers_to_run)} scraper(s))")
    else:
        scrapers_to_run = DEFAULT_FLEET
        print(f"Running default fleet ({len(scrapers_to_run)} scrapers: C63, E55, RS4 B8.5, RS4 B9)")

    totals = {"total": 0}

    for cfg in scrapers_to_run:
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        try:
            results = run(cfg)
            totals["total"] += len(results)
        except Exception as e:
            print(f"  [ERROR running scraper {label}]: {e}")
        time.sleep(2)   # brief pause between scrapers

    print(f"\n{'='*60}")
    print(f"  ALL DONE — {totals['total']} listings processed across {len(scrapers_to_run)} scrapers")
    print(f"{'='*60}")
