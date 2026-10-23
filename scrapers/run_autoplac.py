"""Run autoplac.pl scrapers.

Usage:
    python scrapers/run_autoplac.py              # runs all autoplac models
    python scrapers/run_autoplac.py x3_m40i      # runs only BMW X3 M40i
    python scrapers/run_autoplac.py bmw          # runs all BMW / Alpina models
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
from autoplac.bmw_x3_m_f97 import CONFIG as X3_M_AUTOPLAC
from autoplac.bmw_m2_f87 import CONFIG as M2_F87_AUTOPLAC
from autoplac.bmw_m2_g87 import CONFIG as M2_G87_AUTOPLAC
from autoplac.bmw_m3_f80 import CONFIG as M3_F80_AUTOPLAC
from autoplac.bmw_m3_e46 import CONFIG as M3_E46_AUTOPLAC
from autoplac.bmw_m4_f82 import CONFIG as M4_F82_AUTOPLAC
from autoplac.bmw_1m_e82 import CONFIG as ONE_M_E82_AUTOPLAC
from autoplac.bmw_135i_e82 import CONFIG as I135_E82_AUTOPLAC
from autoplac.bmw_m5_e39 import CONFIG as M5_E39_AUTOPLAC
from autoplac.bmw_z3_m_coupe import CONFIG as Z3_M_AUTOPLAC
from autoplac.bmw_alpina import CONFIG as ALPINA_AUTOPLAC

BMW_FLEET = [
    X3_M40I_AUTOPLAC,
    X3_M_AUTOPLAC,
    M2_F87_AUTOPLAC,
    M2_G87_AUTOPLAC,
    M3_F80_AUTOPLAC,
    M3_E46_AUTOPLAC,
    M4_F82_AUTOPLAC,
    ONE_M_E82_AUTOPLAC,
    I135_E82_AUTOPLAC,
    M5_E39_AUTOPLAC,
    Z3_M_AUTOPLAC,
    ALPINA_AUTOPLAC,
]

ALL_AUTOPLAC_FLEET = BMW_FLEET

SCRAPER_MAP = {
    "x3_m40i":  [X3_M40I_AUTOPLAC],
    "m40i":     [X3_M40I_AUTOPLAC],
    "x3m":      [X3_M_AUTOPLAC],
    "x3_m":     [X3_M_AUTOPLAC],
    "m2":       [M2_F87_AUTOPLAC, M2_G87_AUTOPLAC],
    "m2_f87":   [M2_F87_AUTOPLAC],
    "m2_g87":   [M2_G87_AUTOPLAC],
    "m3":       [M3_F80_AUTOPLAC, M3_E46_AUTOPLAC],
    "m3_f80":   [M3_F80_AUTOPLAC],
    "m3_e46":   [M3_E46_AUTOPLAC],
    "m4":       [M4_F82_AUTOPLAC],
    "1m":       [ONE_M_E82_AUTOPLAC],
    "135i":     [I135_E82_AUTOPLAC],
    "m5":       [M5_E39_AUTOPLAC],
    "m5_e39":   [M5_E39_AUTOPLAC],
    "z3_m":     [Z3_M_AUTOPLAC],
    "alpina":   [ALPINA_AUTOPLAC],
    "bmw":      BMW_FLEET,
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
    failed_models = []
    for i, cfg in enumerate(scrapers_to_run):
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        print(f"\n--- [{i+1}/{len(scrapers_to_run)}] {label} (autoplac) ---")
        try:
            total += len(run(cfg, post_to_api=True))
        except Exception as e:
            print(f"Error running {label}: {e}")
            failed_models.append(label)
            _log_run("error", f"Scraper '{label}' failed: {e}", source="autoplac")
        if (i + 1) < len(scrapers_to_run):
            time.sleep(random.uniform(2, 5))

    print(f"\nALL AUTOPLAC DONE — {total} listings processed.")

    # Batch summary, like run_all.py does for Otomoto
    if len(scrapers_to_run) > 1:
        n = len(scrapers_to_run)
        if failed_models:
            status = "error"
            msg = f"Scheduled run finished with errors: {len(failed_models)}/{n} failed ({', '.join(failed_models)})."
        else:
            status = "success"
            msg = f"Scheduled run completed successfully: all {n} scrapers finished."
        _log_run(status, f"{msg} Processed {total} listings.", processed=total, source="autoplac")
