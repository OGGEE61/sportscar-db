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

from olx.porsche_cayman_987 import CONFIG as CAYMAN_987_OLX
from olx.porsche_cayman_981 import CONFIG as CAYMAN_981_OLX
from olx.porsche_cayman_718 import CONFIG as CAYMAN_718_OLX
from olx.porsche_cayman_gt4_981 import CONFIG as CAYMAN_GT4_OLX
from olx.toyota_gr_yaris import CONFIG as GR_YARIS_OLX
from olx.honda_s2000 import CONFIG as S2000_OLX
from olx.audi_rs4_b85 import CONFIG as RS4_B85_OLX
from olx.audi_rs4_b9 import CONFIG as RS4_B9_OLX
from olx.mercedes_a45_w176 import CONFIG as A45_W176_OLX
from olx.mercedes_gla45_x156 import CONFIG as GLA45_X156_OLX
from olx.mercedes_cl55_c215 import CONFIG as CL55_C215_OLX
from olx.mercedes_clk63_w209 import CONFIG as CLK63_W209_OLX
from olx.mercedes_cls55_c219 import CONFIG as CLS55_C219_OLX
from olx.mercedes_e55_w211 import CONFIG as E55_W211_OLX
from olx.mercedes_g55_w463 import CONFIG as G55_W463_OLX
from olx.mercedes_s55_w220 import CONFIG as S55_W220_OLX

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
    CAYMAN_987_OLX,
    CAYMAN_981_OLX,
    CAYMAN_718_OLX,
    CAYMAN_GT4_OLX,
    GR_YARIS_OLX,
    S2000_OLX,
    RS4_B85_OLX,
    RS4_B9_OLX,
    A45_W176_OLX,
    GLA45_X156_OLX,
    CL55_C215_OLX,
    CLK63_W209_OLX,
    CLS55_C219_OLX,
    E55_W211_OLX,
    G55_W463_OLX,
    S55_W220_OLX,
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
    "cayman_987": [CAYMAN_987_OLX],
    "987": [CAYMAN_987_OLX],
    "cayman_981": [CAYMAN_981_OLX],
    "981": [CAYMAN_981_OLX],
    "cayman_718": [CAYMAN_718_OLX],
    "718": [CAYMAN_718_OLX],
    "gt4": [CAYMAN_GT4_OLX],
    "cayman_gt4": [CAYMAN_GT4_OLX],
    "gr_yaris": [GR_YARIS_OLX],
    "s2000": [S2000_OLX],
    "rs4_b85": [RS4_B85_OLX],
    "rs4_b9": [RS4_B9_OLX],
    "cayman":   [CAYMAN_987_OLX, CAYMAN_981_OLX, CAYMAN_718_OLX, CAYMAN_GT4_OLX],
    "rs4":      [RS4_B85_OLX, RS4_B9_OLX],
    "a45": [A45_W176_OLX],
    "gla45": [GLA45_X156_OLX],
    "cl55": [CL55_C215_OLX],
    "clk63": [CLK63_W209_OLX],
    "cls55": [CLS55_C219_OLX],
    "e55": [E55_W211_OLX],
    "g55": [G55_W463_OLX],
    "s55": [S55_W220_OLX],
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
