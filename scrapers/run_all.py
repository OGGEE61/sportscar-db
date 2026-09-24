"""Run scrapers in sequence or selectively with rotation schedule.

Usage:
    python scrapers/run_all.py              # runs today's scheduled rotation (~2-3 models)
    python scrapers/run_all.py rotation     # runs today's scheduled rotation
    python scrapers/run_all.py all          # runs all fleet scrapers
    python scrapers/run_all.py c63          # runs only C63 W204
    python scrapers/run_all.py e55          # runs only E55 W211
    python scrapers/run_all.py rs4_b85      # runs only RS4 B8.5 Avant
    python scrapers/run_all.py rs4_b9       # runs only RS4 B9 Avant
    python scrapers/run_all.py rs4          # runs both RS4 scrapers (B8.5 and B9)
    python scrapers/run_all.py m4           # runs BMW M4 F82
"""
import sys
import os
import time
import random
from datetime import datetime

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
from bmw_x3_m_f97       import CONFIG    as X3_M
from mercedes_c63_w204  import CONFIG    as C63
from mercedes_e55_w211  import CONFIG    as E55

# Active target fleet
ALL_FLEET = [C63, E55, RS4_B85, RS4_B9, M4, X3_M]

# Rotation schedule by weekday (0 = Monday, ..., 6 = Sunday)
# Guarantees each model runs 3 times per week, distributed evenly across days
WEEKDAY_SCHEDULE = {
    0: [E55, RS4_B9],            # Monday
    1: [C63, M4, X3_M],          # Tuesday
    2: [RS4_B85, E55],           # Wednesday
    3: [C63, RS4_B9, X3_M],      # Thursday
    4: [M4, RS4_B85],            # Friday
    5: [C63, E55, RS4_B9],       # Saturday
    6: [RS4_B85, M4, X3_M],      # Sunday
}

SCRAPER_MAP = {
    "c63": [C63],
    "e55": [E55],
    "rs4_b85": [RS4_B85],
    "rs4_b9": [RS4_B9],
    "rs4": [RS4_B85, RS4_B9],
    "m4": [M4],
    "m3": [M3],
    "rs3": [RS3],
    "x3_m": [X3_M],
    "all": ALL_FLEET,
    "fleet": ALL_FLEET,
}

def get_today_rotation():
    weekday = datetime.utcnow().weekday()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday]
    return day_name, WEEKDAY_SCHEDULE.get(weekday, ALL_FLEET)

if __name__ == "__main__":
    target = os.environ.get("SCRAPER_TARGET", "").lower().strip()
    if len(sys.argv) > 1:
        target = sys.argv[1].lower().strip()

    if target in ("all", "fleet"):
        scrapers_to_run = ALL_FLEET
        print(f"Target selected: ALL FLEET ({len(scrapers_to_run)} scrapers: C63, E55, RS4 B8.5, RS4 B9, M4)")
    elif target in SCRAPER_MAP and target not in ("", "rotation"):
        scrapers_to_run = SCRAPER_MAP[target]
        print(f"Target selected: {target} ({len(scrapers_to_run)} scraper(s))")
    else:
        day_name, scrapers_to_run = get_today_rotation()
        print(f"Running scheduled rotation for {day_name} ({len(scrapers_to_run)} scrapers)")

    # Anti-bot jitter: random delay between 5 to 60 seconds before kicking off
    # when running unattended in CI/CD
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        jitter = random.randint(5, 60)
        print(f"Applying startup jitter of {jitter}s...")
        time.sleep(jitter)

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

        # Random pause between 3 to 8 seconds between scrapers
        pause = random.uniform(3.0, 8.0)
        time.sleep(pause)

    print(f"\n{'='*60}")
    print(f"  ALL DONE — {totals['total']} listings processed across {len(scrapers_to_run)} scrapers")
    print(f"{'='*60}")
