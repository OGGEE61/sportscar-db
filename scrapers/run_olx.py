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
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

from base_scraper import run
# Package-qualified: olx/ and otomoto/ share module names (bmw_m3_f80, ...)
from olx.bmw_alpina import CONFIG as ALPINA_OLX
from olx.bmw_x3_m_f97 import CONFIG as X3_M_OLX
from olx.bmw_x3_m40i_g01 import CONFIG as X3_M40I_OLX
from olx.audi_rs3_8v import CONFIG as RS3_8V_OLX
from olx.bmw_m3_f80 import CONFIG as M3_F80_OLX
from olx.bmw_m3_e46 import CONFIG as M3_E46_OLX
from olx.bmw_m4_f82 import CONFIG as M4_F82_OLX
from olx.bmw_m2_f87 import CONFIG as M2_F87_OLX
from olx.bmw_m2_g87 import CONFIG as M2_G87_OLX
from olx.mercedes_c63_w204 import CONFIG as C63_W204_OLX

ALL_OLX_FLEET = [
    ALPINA_OLX,
    X3_M_OLX,
    X3_M40I_OLX,
    RS3_8V_OLX,
    M3_F80_OLX,
    M3_E46_OLX,
    M4_F82_OLX,
    M2_F87_OLX,
    M2_G87_OLX,
    C63_W204_OLX,
]

SCRAPER_MAP = {
    "alpina":   [ALPINA_OLX],
    "x3m":      [X3_M_OLX],
    "x3_m":     [X3_M_OLX],
    "x3_m40i":  [X3_M40I_OLX],
    "m40i":     [X3_M40I_OLX],
    "rs3":      [RS3_8V_OLX],
    "rs3_8v":   [RS3_8V_OLX],
    "m3":       [M3_F80_OLX, M3_E46_OLX],
    "m3_f80":   [M3_F80_OLX],
    "m3_e46":   [M3_E46_OLX],
    "m4":       [M4_F82_OLX],
    "m2":       [M2_F87_OLX, M2_G87_OLX],
    "m2_f87":   [M2_F87_OLX],
    "m2_g87":   [M2_G87_OLX],
    "c63":      [C63_W204_OLX],
    "all":      ALL_OLX_FLEET,
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
