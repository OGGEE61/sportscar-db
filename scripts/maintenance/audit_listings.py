"""Check stored listings against the rules of the scraper that found them (read-only).

A listing in the DB passed the scraper's rules when it was scraped, but rules change and some were
missing (a 156 HP GLA 200 got into the GLA45 search, see base_scraper._outside_search). This checks
every listing again, with the scrapers' own code:
  - the title words (title_must_contain / title_must_not_contain),
  - the model years (min_year / max_year or the search's years),
  - power and engine size against the searches (base_scraper._outside_search),
  - the model's validator (skipped where a reassign rule settles the model by VIN, as in the scrape).
and says where the VIN stands: stored, in the description, behind "Show VIN" (otomoto), or none.

Pending listings that break a rule should be rejected. Rejected listings that break none and have a
VIN to get (in the description, or behind "Show VIN") were rejected only for the VIN: they can go
back to pending, where the reveal job fills it in. Nothing is changed here.

Usage: python scripts/maintenance/audit_listings.py [--status pending|approved|rejected] [--json FILE]
Reads the backend selected by DB_BACKEND (d1 = production).
"""
import contextlib
import importlib
import io
import json
import os
import pkgutil
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
import base_scraper
from base_scraper import VIN_RE, ScraperConfig, _outside_search, _url_year_range
from validation import is_plausible_vin

SOURCES = ("otomoto", "olx", "autoplac")


def load_configs() -> dict:
    """(scraper source, model, variant) -> [ScraperConfig], from every scraper module."""
    configs = defaultdict(list)
    for pkg in SOURCES:
        package = importlib.import_module(pkg)
        for m in pkgutil.iter_modules(package.__path__):
            if m.name.startswith("_"):
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                module = importlib.import_module(f"{pkg}.{m.name}")
            for name, cfg in vars(module).items():
                if name.startswith("CONFIG") and isinstance(cfg, ScraperConfig):
                    configs[(cfg.source, cfg.model, cfg.variant)].append(cfg)
    return configs


def _quiet(fn, *args):
    """fn(*args) and the last line it printed (validators print why they reject)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    lines = out.getvalue().strip().splitlines()
    return result, (lines[-1].strip() if lines else "")


def broken_rules(listing: dict, cfg: ScraperConfig) -> list:
    """The rules of cfg the stored listing breaks, as short reasons; [] if it passes them all."""
    reasons = []
    title = (listing.get("raw_title") or "").lower().replace(" ", "")
    if cfg.title_must_contain:
        needles = cfg.title_must_contain if isinstance(cfg.title_must_contain, list) else [cfg.title_must_contain]
        if not any(n.lower().replace(" ", "") in title for n in needles):
            reasons.append("title lacks the model name")
    bad = [w for w in cfg.title_must_not_contain if w.lower().replace(" ", "") in title]
    if bad:
        reasons.append(f"title has '{bad[0]}'")

    year = listing.get("year")
    if year:
        urls = [cfg.list_url] if isinstance(cfg.list_url, str) else list(cfg.list_url)
        def outside(url):
            lo, hi = cfg.min_year or _url_year_range(url)[0], cfg.max_year or _url_year_range(url)[1]
            return (lo and year < lo) or (hi and year > hi)
        if urls and all(outside(u) for u in urls):
            reasons.append(f"year {year} outside the searched years")

    if why := _outside_search(cfg, listing):
        reasons.append(why)

    detail = dict(listing, title=listing.get("raw_title"))
    vetted = False
    if cfg.reassign:
        target, _ = _quiet(cfg.reassign, detail)
        vetted = bool(target) and (target.model, target.variant) == (cfg.model, cfg.variant)
    if cfg.validator and not vetted:
        ok, said = _quiet(cfg.validator, detail)
        if not ok:
            reasons.append("validator: " + (said[:90] or "rejects it"))
    return reasons


def vin_state(listing: dict) -> str:
    """'stored', 'in_description', 'behind_reveal' (otomoto "Show VIN") or 'none'."""
    if is_plausible_vin(listing.get("vin") or ""):
        return "stored"
    desc = re.sub(r"<[^>]+>", " ", listing.get("raw_description") or "")
    if any(not re.fullmatch(r"[0-9A-F]{17}", c) and is_plausible_vin(c) for c in VIN_RE.findall(desc)):
        return "in_description"
    if listing.get("source") == "otomoto" and listing.get("vin_confidence") == "found_in_schema":
        return "behind_reveal"
    return "none"


def audit(listing: dict, configs: dict) -> dict:
    """{"broken": [...], "vin": vin_state, "verdict": ...} for one stored listing.

    The listing is checked against the scrapers of its model run by the site that found it; it
    passes if it passes one of them (a model may have several searches).
    """
    finder = listing.get("found_by") or listing.get("source")
    key = (listing.get("model"), listing.get("variant"))
    cfgs = configs.get((finder, *key)) or [c for (s, *k), cs in configs.items() if tuple(k) == key for c in cs]
    broken = min((broken_rules(listing, c) for c in cfgs), key=len) if cfgs else ["no scraper for this model"]
    vin = vin_state(listing)
    status = listing.get("status")
    if status == "pending" and broken:
        verdict = "reject"
    elif status == "rejected" and not broken and vin in ("in_description", "behind_reveal"):
        verdict = "restore"
    elif status == "approved" and broken:
        verdict = "check"
    else:
        verdict = "ok"
    return {"broken": broken, "vin": vin, "verdict": verdict}


def main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    import db

    status = sys.argv[sys.argv.index("--status") + 1] if "--status" in sys.argv else None
    out_file = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    configs = load_configs()
    conn = db.get_db()
    sql = "SELECT * FROM pending_listings" + (" WHERE status = ?" if status else "") + " ORDER BY id"
    rows = [dict(r) for r in conn.execute(sql, (status,) if status else ()).fetchall()]
    conn.close()

    report = []
    for r in rows:
        report.append({"id": r["id"], "status": r["status"], "variant": r["variant"],
                       "title": (r["raw_title"] or "")[:60], "year": r["year"], "power_hp": r["power_hp"],
                       "engine_cc": r["engine_cc"], "url": r["source_url"], **audit(r, configs)})

    for st in ("pending", "approved", "rejected"):
        group = [x for x in report if x["status"] == st]
        if not group:
            continue
        print(f"\n{st}: {len(group)} listings | VIN: {dict(Counter(x['vin'] for x in group))}")
        flagged = [x for x in group if x["verdict"] != "ok"]
        label = {"reject": "breaks a rule, reject", "restore": "rejected only for the VIN, which can be had",
                 "check": "approved but breaks a rule (rule added later?)"}
        for verdict in ("reject", "restore", "check"):
            hits = [x for x in flagged if x["verdict"] == verdict]
            if hits:
                print(f"  {len(hits)} {label[verdict]}:")
                for x in hits:
                    print(f"    {x['id']} {x['variant']} | {x['title'][:45]} | {x['year']} | "
                          f"{x['power_hp']} HP | {'; '.join(x['broken']) or 'VIN ' + x['vin']}")
    if out_file:
        with open(out_file, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print(f"\nDetails: {out_file}")


if __name__ == "__main__":
    main()
