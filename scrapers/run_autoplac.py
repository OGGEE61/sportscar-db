"""Run autoplac.pl scrapers.

Usage:
    python scrapers/run_autoplac.py              # runs all autoplac models
    python scrapers/run_autoplac.py x3_m40i      # runs only BMW X3 M40i
"""
import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

from base_scraper import run, _log_run
# Package-qualified: autoplac/ shares module names with olx/ and otomoto/
from autoplac.bmw_x3_m40i_g01 import CONFIG as X3_M40I_AUTOPLAC

ALL_AUTOPLAC_FLEET = [
    X3_M40I_AUTOPLAC,
]

SCRAPER_MAP = {
    "x3_m40i":  [X3_M40I_AUTOPLAC],
    "m40i":     [X3_M40I_AUTOPLAC],
    "all":      ALL_AUTOPLAC_FLEET,
}

if __name__ == "__main__":
    target = os.getenv("SCRAPER_TARGET")
    if not target and len(sys.argv) > 1:
        target = sys.argv[1].lower()
    if not target:
        target = "all"

    scrapers_to_run = SCRAPER_MAP.get(target, ALL_AUTOPLAC_FLEET)
    print(f"Running autoplac scraper target: {target} ({len(scrapers_to_run)} scraper(s))")

    total = 0
    for i, cfg in enumerate(scrapers_to_run):
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        print(f"\n--- [{i+1}/{len(scrapers_to_run)}] {label} (autoplac) ---")
        try:
            total += len(run(cfg, post_to_api=True))
        except Exception as e:
            print(f"Error running {label}: {e}")
            _log_run("error", f"Scraper '{label}' failed: {e}", source="autoplac")
        if (i + 1) < len(scrapers_to_run):
            time.sleep(random.uniform(2, 5))

    print(f"\nALL AUTOPLAC DONE — {total} listings processed.")
