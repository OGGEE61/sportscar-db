"""Live check that our list-page paging fetches every listing the site reports. Posts nothing.

For each scraper's search, drops all filters (keeps only the make/model path), then compares
  site   the result count the site itself reports for that unfiltered search
  walked unique ads our paging loop collects from the same pages (run()'s stop rules, no detail pages)
and, for context, how many of those the scraper's own filters and title guard keep.

  FAIL  walked < site (ads missed by paging), or a list page errored
  WARN  walked > site (site count is approximate)

Usage:
    python scripts/verify_coverage.py                  # every otomoto scraper
    python scripts/verify_coverage.py m2 cayman        # only scrapers whose file name matches
    python scripts/verify_coverage.py --source olx
"""
import argparse
import importlib
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scrapers"))
sys.path.insert(0, ROOT)

from bs4 import BeautifulSoup  # noqa: E402
from curl_cffi import requests  # noqa: E402

import base_scraper  # noqa: E402


def unfiltered(list_url: str) -> str:
    """Same search path with every query filter removed."""
    p = urlsplit(list_url)
    return f"{p.scheme}://{p.netloc}{p.path}?page={{page}}"


def site_total(source: str, html: str):
    if source == "otomoto":
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        for val in json.loads(m.group(1))["props"]["pageProps"]["urqlState"].values():
            raw = val.get("data") or "{}"
            data = json.loads(raw) if isinstance(raw, str) else raw
            if "advertSearch" in data:
                return data["advertSearch"].get("totalCount")
        return None
    m = re.search(r"Znaleźliśmy\s+([\d\s\xa0]+?)\s*ogłosz", html)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def walk(source: str, url_tmpl: str, delay: float):
    """Page through a search like run() does. Returns (site_total, cards, error)."""
    total, seen, cards = None, set(), []
    for page in range(1, 201):
        if total is not None and len(seen) >= total:
            break
        r = requests.get(url_tmpl.format(page=page), headers=base_scraper.HEADERS,
                         timeout=15, impersonate="chrome")
        if r.status_code != 200:
            return total, cards, f"HTTP {r.status_code} on page {page}"
        soup = BeautifulSoup(r.text, "html.parser")
        if source == "otomoto":
            page_cards = base_scraper._parse_otomoto_cards(soup, r.text)
        else:
            page_cards = base_scraper._parse_olx_cards(soup)
        if total is None:
            total = site_total(source, r.text)
            if total == 0:
                break
        ids = {c["listing_id"] for c in page_cards}
        if not page_cards or ids <= seen:
            break
        seen |= ids
        cards += [c for c in page_cards if c["listing_id"] in ids]
        time.sleep(delay)
    return total, cards, None


def kept_by_title(cfg, cards):
    needles = cfg.title_must_contain if isinstance(cfg.title_must_contain, list) else [cfg.title_must_contain]
    bad = cfg.title_must_not_contain or []
    out = []
    for c in cards:
        hay = c["title"].lower().replace(" ", "")
        if cfg.title_must_contain and not any(n.lower().replace(" ", "") in hay for n in needles):
            continue
        if any(b.lower().replace(" ", "") in hay for b in bad):
            continue
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="substrings of scraper file names")
    ap.add_argument("--source", default="otomoto", choices=["otomoto", "olx"])
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    folder = os.path.join(ROOT, "scrapers", args.source)
    mods = sorted(f[:-3] for f in os.listdir(folder) if f.endswith(".py") and not f.startswith("_"))
    mods = [m for m in mods if m != "__init__" and (not args.names or any(n in m for n in args.names))]

    done, fails = {}, 0
    print(f"{'scraper':26} {'site':>5} {'walked':>6} {'filtered-search':>15}  verdict")
    for name in mods:
        mod = importlib.import_module(f"{args.source}.{name}")
        # most files define CONFIG; a few (bmw_m4_f82) use a model-specific name
        cfg = getattr(mod, "CONFIG", None) or getattr(mod, next(n for n in dir(mod) if n.startswith("CONFIG_")))
        url = cfg.list_url if isinstance(cfg.list_url, str) else cfg.list_url[0]
        base = unfiltered(url)
        if base not in done:
            done[base] = walk(args.source, base, args.delay)
        total, cards, err = done[base]
        kept = len(kept_by_title(cfg, cards))
        if err or total is None or len(cards) < total:
            verdict, fails = f"FAIL {err or ''}", fails + 1
        elif len(cards) > total:
            verdict = "WARN walked > site"
        else:
            verdict = "ok"
        print(f"{name:26} {total!s:>5} {len(cards):>6} {kept:>15}  {verdict}")
    print(f"\n{fails} failing search(es). 'filtered-search' = unfiltered ads left by the title guard "
          f"(the year/engine filters in the scraper URL narrow it further).")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
