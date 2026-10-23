"""Live check that every autoplac scraper fetches the right model. Posts nothing.

Runs the scrapers against autoplac.pl (post_to_api=False) and checks each kept listing
against expectations written here, independent of the scrapers' own validators:

  FAIL  VIN maker code of another make, year outside the scraper's range, the same ad
        kept under two models, or a list page that errored / came back without data
  WARN  power or engine size outside what the model can have (tuned cars, typos)

Usage:
    python scripts/verify_autoplac.py                 # all 35 scrapers
    python scripts/verify_autoplac.py bmw mercedes    # run_autoplac.py targets
    python scripts/verify_autoplac.py --cache c.json  # reuse detail pages from earlier runs
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scrapers"))
sys.path.insert(0, ROOT)

import base_scraper  # noqa: E402
import run_autoplac  # noqa: E402

# VIN maker codes (first 3 characters) per make; Alpina builds its own cars (WAP)
MAKE_WMI = {
    "BMW":           ("WBA", "WBS", "WBY", "WBX", "5UX", "5YM", "3MW", "3MF", "WB1"),
    "Alpina":        ("WAP",),
    "Mercedes-Benz": ("WDB", "WDC", "WDD", "WDF", "W1K", "W1N", "W1V", "4JG", "55S"),
    "Audi":          ("WAU", "WUA", "TRU", "WA1"),
    "Porsche":       ("WP0", "WP1"),
    "Toyota":        ("JTD", "JTM", "JTE", "SB1", "VNK", "JT"),
    "Honda":         ("JHM", "JH4", "JHL", "1HG", "2HG", "SHH", "SHS"),
}

# (model, variant) -> power range in HP, engine size range in cm3 (None = any)
EXPECT = {
    ("X3", "M40i G01"):                (320, 430, 2900, 3100),
    ("X3 M", "F97"):                   (440, 560, 2900, 3100),
    ("M2", "F87"):                     (360, 470, 2900, 3100),
    ("M2", "G87"):                     (440, 520, 2900, 3100),
    ("M3", "F80"):                     (420, 480, 2900, 3100),
    ("M3", "E46 M3"):                  (330, 370, 3200, 3300),
    ("M4", "F82"):                     (420, 520, 2900, 3100),
    ("Seria 1", "1M E82"):             (330, 350, 2900, 3100),
    ("Seria 1", "135i E82/E88"):       (300, 335, 2900, 3100),
    ("M5", "E39 M5"):                  (390, 410, 4900, 5000),
    ("Z3", "Z3 M"):                    (240, 330, 3100, 3300),
    ("BMW", "Alpina"):                 (None, None, None, None),
    ("Klasa C", "W204 C63 AMG"):       (440, 540, 6000, 6300),
    ("Klasa E", "W211 E55 AMG"):       (460, 520, 5300, 5500),
    ("CLS", "C219 CLS 55 AMG"):        (460, 520, 5300, 5500),
    ("Klasa CLK", "W209 CLK 63 AMG"):  (470, 520, 6000, 6300),
    ("Klasa A", "A45 AMG W176"):       (350, 400, 1900, 2000),
    ("GLA", "GLA45 AMG X156"):         (350, 400, 1900, 2000),
    ("Klasa G", "G55 AMG W463"):       (450, 520, 5300, 5600),
    ("Klasa S", "S55 AMG W220"):       (450, 520, 5300, 5500),
    ("SL", "SL55 AMG R230"):           (450, 520, 5300, 5500),
    ("CL", "CL55 AMG C215"):           (450, 520, 5300, 5500),
    ("RS3", "8V"):                     (360, 430, 2400, 2500),
    ("RS4", "B8.5 Avant"):             (440, 460, 4100, 4300),
    ("RS4", "B9 Avant"):               (440, 460, 2800, 3000),
    ("TT", "TT RS"):                   (330, 420, 2400, 2600),
    ("R8", "R8 V8"):                   (400, 440, 4100, 4300),
    ("R8", "R8 V10"):                  (500, 630, 5100, 5300),
    ("Cayman", "Cayman 987"):          (290, 340, 3300, 3500),
    ("Cayman", "Cayman 981"):          (320, 350, 3300, 3500),
    ("Cayman", "981 GT4"):             (380, 390, 3700, 3900),
    ("718", "718 Cayman"):             (345, 520, None, None),
    ("Macan", "Macan Gen 1 (GTS/Turbo)"): (355, 450, 2900, 3700),
    ("GR Yaris", "GR Yaris"):          (250, 280, 1500, 1700),
    ("S2000", "S2000"):                (230, 250, 1900, 2300),
}


def fleet_targets(names):
    if not names:
        return run_autoplac.ALL_AUTOPLAC_FLEET
    seen, out = set(), []
    for n in names:
        for cfg in run_autoplac.SCRAPER_MAP[n.lower()]:
            if id(cfg) not in seen:
                seen.add(id(cfg))
                out.append(cfg)
    return out


def out_of(value, lo, hi):
    return value is not None and ((lo is not None and value < lo) or (hi is not None and value > hi))


def check_listing(cfg_by_key, r):
    """(fails, warns) for one kept listing."""
    fails, warns = [], []
    key = (r["model"], r["variant"])
    exp_cfg = cfg_by_key.get(key)
    if not exp_cfg:
        return [f"saved as unknown model {key}"], []
    vin = (r.get("vin") or "").upper()
    if vin and not vin.startswith(MAKE_WMI.get(r["make"], ())):
        fails.append(f"VIN {vin[:3]}... is not a {r['make']}")
    year = r.get("year")
    if year and ((exp_cfg.min_year and year < exp_cfg.min_year) or (exp_cfg.max_year and year > exp_cfg.max_year)):
        fails.append(f"year {year} outside {exp_cfg.min_year}-{exp_cfg.max_year}")
    p_lo, p_hi, c_lo, c_hi = EXPECT.get(key, (None,) * 4)
    if out_of(r.get("power_hp"), p_lo, p_hi):
        warns.append(f"power {r['power_hp']} HP outside {p_lo}-{p_hi}")
    if out_of(r.get("engine_cc"), c_lo, c_hi):
        warns.append(f"engine {r['engine_cc']} cm3 outside {c_lo}-{c_hi}")
    return fails, warns


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="run_autoplac.py targets (default: all)")
    ap.add_argument("--cache", help="JSON file of detail pages: read first, written after the run")
    ap.add_argument("--verbose", action="store_true", help="print each scraper's own output")
    args = ap.parse_args()

    base_scraper._log_run = lambda *a, **k: None
    if args.cache and os.path.exists(args.cache):
        base_scraper._DETAIL_CACHE.update(json.load(open(args.cache)))
        print(f"[cache] {len(base_scraper._DETAIL_CACHE)} detail pages loaded")

    fleet = fleet_targets(args.targets)
    cfg_by_key = {(c.model, c.variant): c for c in run_autoplac.ALL_AUTOPLAC_FLEET}
    kept_by_id = defaultdict(set)      # listing id -> {(model, variant)}
    all_fails, all_warns, rows = [], [], []

    for i, cfg in enumerate(fleet, 1):
        label = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        print(f"[{i}/{len(fleet)}] {label} ...", flush=True)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                results = base_scraper.run(cfg, post_to_api=False)
        except Exception as e:
            all_fails.append(f"{label}: crashed: {e!r}")
            continue
        log = buf.getvalue()
        if args.verbose:
            print(log)
        for bad in re.findall(r"^.*(?:HTTP \d+ -- stopping|No autoplac search data|\[list error\]|\[detail error\]).*$", log, re.M):
            all_fails.append(f"{label}: {bad.strip()}")

        cards = int((re.search(r"Done\. (\d+) cards seen", log) or [0, 0])[1])
        rejects = Counter(re.findall(r"\[((?:reject|skip)[a-z0-9-]*)\]", log))
        reassigned = len(re.findall(r"\[reassign\]", log))
        vins = sum(1 for r in results if r.get("vin"))
        plates = sum(1 for r in results if r.get("registration_plate"))
        years = [r["year"] for r in results if r.get("year")]
        powers = [r["power_hp"] for r in results if r.get("power_hp")]
        for r in results:
            kept_by_id[r["source_listing_id"]].add((r["model"], r["variant"]))
            fails, warns = check_listing(cfg_by_key, r)
            tag = f"{label}: {r['source_listing_id']} {r.get('raw_title', '')[:50]!r} {r.get('year')}"
            all_fails += [f"{tag}: {f}" for f in fails]
            all_warns += [f"{tag}: {w}" for w in warns]
        rows.append((label, cards, len(results), vins, plates, reassigned, sum(rejects.values()),
                     f"{min(years)}-{max(years)}" if years else "-",
                     f"{min(powers)}-{max(powers)}" if powers else "-"))

    for sid, keys in kept_by_id.items():
        if len(keys) > 1:
            all_fails.append(f"ad {sid} kept under {len(keys)} models: {sorted(keys)}")

    if args.cache:
        json.dump(base_scraper._DETAIL_CACHE, open(args.cache, "w"))

    print("\n%-44s %5s %5s %4s %5s %6s %7s %-11s %-9s" % (
        "scraper", "cards", "kept", "VIN", "plate", "reasgn", "reject", "years", "power"))
    for row in rows:
        print("%-44s %5d %5d %4d %5d %6d %7d %-11s %-9s" % row)
    print(f"\n{len(all_warns)} warning(s):")
    for w in all_warns:
        print("  WARN", w)
    print(f"\n{len(all_fails)} failure(s):")
    for f in all_fails:
        print("  FAIL", f)
    sys.exit(1 if all_fails else 0)


if __name__ == "__main__":
    main()
