"""Run scrapers in sequence or selectively with rotation schedule.

Usage:
    python scrapers/run_all.py              # runs scheduled single model for current 2h slot
    python scrapers/run_all.py single       # runs scheduled single model for current 2h slot
    python scrapers/run_all.py next_2       # runs next 2 scheduled models in sequence
    python scrapers/run_all.py next_3       # runs next 3 scheduled models in sequence
    python scrapers/run_all.py batch        # runs today's scheduled weekday batch
    python scrapers/run_all.py all          # runs all fleet scrapers
    python scrapers/run_all.py c63          # runs only C63 W204
    python scrapers/run_all.py e55          # runs only E55 W211
    python scrapers/run_all.py cls55        # runs only CLS 55 AMG
    python scrapers/run_all.py rs4_b85      # runs only RS4 B8.5 Avant
    python scrapers/run_all.py rs4_b9       # runs only RS4 B9 Avant
    python scrapers/run_all.py rs4          # runs both RS4 scrapers (B8.5 and B9)
    python scrapers/run_all.py m4           # runs BMW M4 F82
    python scrapers/run_all.py gr_yaris     # runs Toyota GR Yaris
"""
import sys
import os
import time
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "otomoto"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

from base_scraper import run, _log_run

from audi_rs3_8v          import CONFIG    as RS3
from audi_rs4_b85         import CONFIG    as RS4_B85
from audi_rs4_b9          import CONFIG    as RS4_B9
from audi_ttrs            import CONFIG    as TTRS
from bmw_m2_f87           import CONFIG    as M2_F87
from bmw_m2_g87           import CONFIG    as M2_G87
from bmw_m3_f80           import CONFIG    as M3
from bmw_m4_f82           import CONFIG_M4 as M4
from bmw_x3_m_f97         import CONFIG    as X3_M
from bmw_x3_m40i_g01      import CONFIG    as X3_M40I
from mercedes_c63_w204    import CONFIG    as C63
from mercedes_e55_w211    import CONFIG    as E55
from mercedes_cls55_c219  import CONFIG    as CLS55
from mercedes_clk63_w209  import CONFIG    as CLK63
from porsche_cayman_gt4_981 import CONFIG  as CAYMAN_GT4
from toyota_gr_yaris      import CONFIG    as GR_YARIS
from bmw_alpina           import CONFIG    as ALPINA

from bmw_m3_e46           import CONFIG    as M3_E46
from bmw_1m_e82           import CONFIG    as M1_E82
from bmw_135i_e82         import CONFIG    as BMW_135I
from bmw_z3_m_coupe       import CONFIG    as Z3_M
from bmw_m5_e39           import CONFIG    as M5_E39

from audi_r8_v8           import CONFIG    as R8_V8
from audi_r8_v10          import CONFIG    as R8_V10
from mercedes_a45_w176    import CONFIG    as A45
from mercedes_gla45_x156  import CONFIG    as GLA45
from mercedes_g55_w463    import CONFIG    as G55
from mercedes_s55_w220    import CONFIG    as S55
from mercedes_sl55_r230   import CONFIG    as SL55
from mercedes_cl55_c215   import CONFIG    as CL55

from porsche_cayman_987   import CONFIG    as CAYMAN_987
from porsche_cayman_981   import CONFIG    as CAYMAN_981
from porsche_cayman_718   import CONFIG    as CAYMAN_718
from porsche_macan_gen1   import CONFIG    as MACAN_G1
from honda_s2000          import CONFIG    as S2000

# Active target fleet
ALL_FLEET = [
    C63, E55, CLS55, CLK63,
    RS4_B85, RS4_B9, RS3, TTRS,
    M2_F87, M2_G87, M3, M4, X3_M, X3_M40I,
    CAYMAN_GT4,
    GR_YARIS,
    ALPINA,
    M3_E46, M1_E82, BMW_135I, Z3_M, M5_E39,
    R8_V8, R8_V10,
    A45, GLA45, G55, S55, SL55, CL55,
    CAYMAN_987, CAYMAN_981, CAYMAN_718, MACAN_G1,
    S2000,
]

# Dynamically distribute 3 runs per week for every scraper across the 7 days
WEEKDAY_SCHEDULE = {i: [] for i in range(7)}
_all_runs = ALL_FLEET * 3
import random
_rnd = random.Random(42) # Fixed seed so schedule is stable
_rnd.shuffle(_all_runs)

for i, scraper in enumerate(_all_runs):
    WEEKDAY_SCHEDULE[i % 7].append(scraper)

SCRAPER_MAP = {
    "alpina": [ALPINA],
    "c63": [C63],
    "e55": [E55],
    "cls55": [CLS55],
    "clk63": [CLK63],
    "gr_yaris": [GR_YARIS],
    "ttrs": [TTRS],
    "m2_f87": [M2_F87],
    "m2_g87": [M2_G87],
    "m2": [M2_F87, M2_G87],
    "m3": [M3, M3_E46],
    "m3_e46": [M3_E46],
    "m4": [M4],
    "m5": [M5_E39],
    "m5_e39": [M5_E39],
    "1m": [M1_E82],
    "135i": [BMW_135I],
    "z3_m": [Z3_M],
    "rs3": [RS3],
    "rs4_b85": [RS4_B85],
    "rs4_b9": [RS4_B9],
    "rs4": [RS4_B85, RS4_B9],
    "r8_v8": [R8_V8],
    "r8_v10": [R8_V10],
    "r8": [R8_V8, R8_V10],
    "a45": [A45],
    "gla45": [GLA45],
    "g55": [G55],
    "s55": [S55],
    "sl55": [SL55],
    "cl55": [CL55],
    "cayman_gt4": [CAYMAN_GT4],
    "cayman": [CAYMAN_987, CAYMAN_981, CAYMAN_718, CAYMAN_GT4],
    "macan": [MACAN_G1],
    "s2000": [S2000],
    "x3_m": [X3_M],
    "x3_m40i": [X3_M40I],
    "all": ALL_FLEET,
    "fleet": ALL_FLEET,
}

def get_today_rotation():
    weekday = datetime.utcnow().weekday()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday]
    return day_name, WEEKDAY_SCHEDULE.get(weekday, ALL_FLEET)

def get_scheduled_models(count: int = 1, interval_hours: int = 2):
    """Deterministically pick `count` consecutive models based on current time slot.
    Rotates continuously across ALL_FLEET (35 models every ~70 hours).
    """
    slot = int(time.time() // (interval_hours * 3600))
    selected = []
    for offset in range(count):
        idx = (slot + offset) % len(ALL_FLEET)
        cfg = ALL_FLEET[idx]
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        selected.append((cfg, idx, label))
    return selected

if __name__ == "__main__":
    target = os.environ.get("SCRAPER_TARGET", "").lower().strip()
    if len(sys.argv) > 1:
        target = sys.argv[1].lower().strip()

    if target in ("all", "fleet"):
        scrapers_to_run = ALL_FLEET
        print(f"Target selected: ALL FLEET ({len(scrapers_to_run)} scrapers)")
    elif target in ("batch", "daily_batch"):
        day_name, scrapers_to_run = get_today_rotation()
        print(f"Target selected: daily batch for {day_name} ({len(scrapers_to_run)} scrapers)")
    elif target in ("next_2", "2", "two", "slot_2", "2_models", "two_models"):
        selected = get_scheduled_models(count=2, interval_hours=2)
        scrapers_to_run = [cfg for cfg, _, _ in selected]
        labels = ", ".join([f"#{idx+1} {label}" for _, idx, label in selected])
        print(f"Target selected: next 2 scheduled slots -> {labels}")
    elif target in ("next_3", "3", "three", "slot_3", "3_models", "three_models"):
        selected = get_scheduled_models(count=3, interval_hours=2)
        scrapers_to_run = [cfg for cfg, _, _ in selected]
        labels = ", ".join([f"#{idx+1} {label}" for _, idx, label in selected])
        print(f"Target selected: next 3 scheduled slots -> {labels}")
    elif target in SCRAPER_MAP and target not in ("", "single", "rotation", "next", "1"):
        scrapers_to_run = SCRAPER_MAP[target]
        print(f"Target selected: {target} ({len(scrapers_to_run)} scraper(s))")
    else:
        selected = get_scheduled_models(count=1, interval_hours=2)
        scrapers_to_run = [selected[0][0]]
        print(f"Target selected: scheduled slot #{selected[0][1] + 1}/{len(ALL_FLEET)} -> {selected[0][2]}")

    # Anti-bot jitter: random delay between 5 to 45 seconds before kicking off
    # when running unattended in CI/CD
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        jitter = random.randint(5, 45)
        print(f"Applying startup jitter of {jitter}s...")
        time.sleep(jitter)

    totals = {"total": 0}
    failed_models = []
    success_count = 0

    for i, cfg in enumerate(scrapers_to_run):
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        print(f"\n{'='*60}")
        print(f"  [{i+1}/{len(scrapers_to_run)}] {label}")
        print(f"{'='*60}")
        try:
            results = run(cfg)
            totals["total"] += len(results)
            success_count += 1
        except Exception as e:
            err_msg = str(e)
            print(f"  [ERROR running scraper {label}]: {err_msg}")
            failed_models.append((label, err_msg))
            _log_run("error", f"Scraper '{label}' failed: {err_msg}")

        # If running 'all', take a long 2-minute break every 10 models to protect cookies
        if target in ("all", "fleet") and (i + 1) % 10 == 0 and (i + 1) < len(scrapers_to_run):
            print("\n[CHUNKING] Taking a 120s cooldown break to protect session cookies...")
            time.sleep(120)
        elif len(scrapers_to_run) > 1 and (i + 1) < len(scrapers_to_run):
            # Standard random pause between 3 to 8 seconds between scrapers
            pause = random.uniform(3.0, 8.0)
            time.sleep(pause)

    print(f"\n{'='*60}")
    print(f"  ALL DONE — {totals['total']} listings processed across {len(scrapers_to_run)} scrapers ({success_count} succeeded, {len(failed_models)} failed)")
    print(f"{'='*60}")

    # Post batch summary log to database only if running multiple models
    if len(scrapers_to_run) > 1:
        summary_status = "error" if failed_models else "success"
        if failed_models:
            failed_names = ", ".join([name for name, _ in failed_models])
            summary_msg = f"Scheduled run finished with errors: {len(failed_models)}/{len(scrapers_to_run)} failed ({failed_names}). Processed {totals['total']} listings."
        else:
            summary_msg = f"Scheduled run completed successfully: all {len(scrapers_to_run)} scrapers finished. Processed {totals['total']} listings."
        _log_run(summary_status, summary_msg, processed=totals["total"])


