"""Run autoplac.pl scrapers.

Usage:
    python scrapers/run_autoplac.py              # runs all autoplac models
    python scrapers/run_autoplac.py x3_m40i      # runs only BMW X3 M40i
    python scrapers/run_autoplac.py bmw          # runs all BMW / Alpina models
    python scrapers/run_autoplac.py mercedes     # also: audi, porsche
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

from base_scraper import run, _log_run, _parse_autoplac_cards, requests, HEADERS
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

from autoplac.mercedes_c63_w204 import CONFIG as C63_W204_AUTOPLAC
from autoplac.mercedes_e55_w211 import CONFIG as E55_W211_AUTOPLAC
from autoplac.mercedes_cls55_c219 import CONFIG as CLS55_C219_AUTOPLAC
from autoplac.mercedes_clk63_w209 import CONFIG as CLK63_W209_AUTOPLAC
from autoplac.mercedes_a45_w176 import CONFIG as A45_W176_AUTOPLAC
from autoplac.mercedes_gla45_x156 import CONFIG as GLA45_X156_AUTOPLAC
from autoplac.mercedes_g55_w463 import CONFIG as G55_W463_AUTOPLAC
from autoplac.mercedes_s55_w220 import CONFIG as S55_W220_AUTOPLAC
from autoplac.mercedes_sl55_r230 import CONFIG as SL55_R230_AUTOPLAC
from autoplac.mercedes_cl55_c215 import CONFIG as CL55_C215_AUTOPLAC

from autoplac.audi_rs3_8v import CONFIG as RS3_8V_AUTOPLAC
from autoplac.audi_rs4_b85 import CONFIG as RS4_B85_AUTOPLAC
from autoplac.audi_rs4_b9 import CONFIG as RS4_B9_AUTOPLAC
from autoplac.audi_ttrs import CONFIG as TTRS_AUTOPLAC
from autoplac.audi_r8_v8 import CONFIG as R8_V8_AUTOPLAC
from autoplac.audi_r8_v10 import CONFIG as R8_V10_AUTOPLAC

from autoplac.porsche_cayman_987 import CONFIG as CAYMAN_987_AUTOPLAC
from autoplac.porsche_cayman_981 import CONFIG as CAYMAN_981_AUTOPLAC
from autoplac.porsche_cayman_gt4_981 import CONFIG as CAYMAN_GT4_AUTOPLAC
from autoplac.porsche_cayman_718 import CONFIG as CAYMAN_718_AUTOPLAC
from autoplac.porsche_macan_gen1 import CONFIG as MACAN_AUTOPLAC

from autoplac.toyota_gr_yaris import CONFIG as GR_YARIS_AUTOPLAC
from autoplac.honda_s2000 import CONFIG as S2000_AUTOPLAC

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

MERCEDES_FLEET = [
    C63_W204_AUTOPLAC,
    E55_W211_AUTOPLAC,
    CLS55_C219_AUTOPLAC,
    CLK63_W209_AUTOPLAC,
    A45_W176_AUTOPLAC,
    GLA45_X156_AUTOPLAC,
    G55_W463_AUTOPLAC,
    S55_W220_AUTOPLAC,
    SL55_R230_AUTOPLAC,
    CL55_C215_AUTOPLAC,
]

AUDI_FLEET = [
    RS3_8V_AUTOPLAC,
    RS4_B85_AUTOPLAC,
    RS4_B9_AUTOPLAC,
    TTRS_AUTOPLAC,
    R8_V8_AUTOPLAC,
    R8_V10_AUTOPLAC,
]

PORSCHE_FLEET = [
    CAYMAN_987_AUTOPLAC,
    CAYMAN_981_AUTOPLAC,
    CAYMAN_GT4_AUTOPLAC,
    CAYMAN_718_AUTOPLAC,
    MACAN_AUTOPLAC,
]

ALL_AUTOPLAC_FLEET = BMW_FLEET + MERCEDES_FLEET + AUDI_FLEET + PORSCHE_FLEET + [
    GR_YARIS_AUTOPLAC,
    S2000_AUTOPLAC,
]

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
    "c63":      [C63_W204_AUTOPLAC],
    "e55":      [E55_W211_AUTOPLAC],
    "cls55":    [CLS55_C219_AUTOPLAC],
    "clk63":    [CLK63_W209_AUTOPLAC],
    "a45":      [A45_W176_AUTOPLAC],
    "gla45":    [GLA45_X156_AUTOPLAC],
    "g55":      [G55_W463_AUTOPLAC],
    "s55":      [S55_W220_AUTOPLAC],
    "sl55":     [SL55_R230_AUTOPLAC],
    "cl55":     [CL55_C215_AUTOPLAC],
    "mercedes": MERCEDES_FLEET,
    "rs3":      [RS3_8V_AUTOPLAC],
    "rs3_8v":   [RS3_8V_AUTOPLAC],
    "rs4":      [RS4_B85_AUTOPLAC, RS4_B9_AUTOPLAC],
    "rs4_b85":  [RS4_B85_AUTOPLAC],
    "rs4_b9":   [RS4_B9_AUTOPLAC],
    "ttrs":     [TTRS_AUTOPLAC],
    "r8":       [R8_V8_AUTOPLAC, R8_V10_AUTOPLAC],
    "r8_v8":    [R8_V8_AUTOPLAC],
    "r8_v10":   [R8_V10_AUTOPLAC],
    "audi":     AUDI_FLEET,
    "cayman":   [CAYMAN_987_AUTOPLAC, CAYMAN_981_AUTOPLAC, CAYMAN_GT4_AUTOPLAC, CAYMAN_718_AUTOPLAC],
    "cayman_987": [CAYMAN_987_AUTOPLAC],
    "987":      [CAYMAN_987_AUTOPLAC],
    "cayman_981": [CAYMAN_981_AUTOPLAC],
    "981":      [CAYMAN_981_AUTOPLAC],
    "gt4":      [CAYMAN_GT4_AUTOPLAC],
    "cayman_gt4": [CAYMAN_GT4_AUTOPLAC],
    "cayman_718": [CAYMAN_718_AUTOPLAC],
    "718":      [CAYMAN_718_AUTOPLAC],
    "macan":    [MACAN_AUTOPLAC],
    "porsche":  PORSCHE_FLEET,
    "gr_yaris": [GR_YARIS_AUTOPLAC],
    "s2000":    [S2000_AUTOPLAC],
    "all":      ALL_AUTOPLAC_FLEET,
}

def preflight(cfg):
    """One cheap request before the fleet. None if autoplac answers with search data,
    else what went wrong.

    autoplac sits behind Cloudflare, which can refuse a whole network (GitHub-hosted
    runners come from Azure): every list page then returns 403 and the fleet would
    "finish" 35 empty scrapers. Better to stop with one clear error.
    """
    url = (cfg.list_url if isinstance(cfg.list_url, str) else cfg.list_url[0]).format(page=1)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, impersonate="chrome")
    except Exception as e:
        return f"request failed: {e}"
    if r.status_code != 200:
        h = r.headers
        return (f"HTTP {r.status_code} (server={h.get('server')}, cf-mitigated={h.get('cf-mitigated')}, "
                f"cf-ray={h.get('cf-ray')}) {r.text[:100]!r}")
    if _parse_autoplac_cards(r.text)[1] is None:
        return "HTTP 200 but the page has no search data (block page or layout change)"
    return None


if __name__ == "__main__":
    target = os.getenv("SCRAPER_TARGET")
    if not target and len(sys.argv) > 1:
        target = sys.argv[1].lower()
    if not target:
        target = "all"

    scrapers_to_run = SCRAPER_MAP.get(target, ALL_AUTOPLAC_FLEET)
    print(f"Running autoplac scraper target: {target} ({len(scrapers_to_run)} scraper(s))")

    problem = preflight(scrapers_to_run[0])
    if problem:
        msg = f"autoplac is not reachable from here, nothing scraped: {problem}"
        print(msg)
        _log_run("error", msg, source="autoplac")
        sys.exit(1)

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
