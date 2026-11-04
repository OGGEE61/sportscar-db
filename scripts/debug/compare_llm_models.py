"""Run local Ollama models over the same listings and write a side-by-side HTML report. Writes nothing to the DB.

Picks a fixed set of awkward ads (US imports, damage, short and long ads, market conflicts, plain ones)
and shows each model next to the summary and market stored today.

Usage:
    DB_BACKEND=d1 python scripts/debug/compare_llm_models.py --out report.html
    DB_BACKEND=d1 python scripts/debug/compare_llm_models.py --out report.html --per-group 5 --models a b
"""
import argparse
import html
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import db
import enrich_with_bielik as enrich

DEFAULT_MODELS = ["SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M", "qwen2.5:7b"]
FIELDS = ["origin_market", "origin_reasoning", "accident_status", "location_region",
          "interior_color", "interior_material", "has_panoramic_roof", "key_equipment", "summary"]
GROUPS = {
    "US/Canada import": "origin_market IN ('USA', 'Kanada', 'USA/Kanada')",
    "damage mentioned": "(raw_description LIKE '%uszkodz%' OR raw_description LIKE '%powypadk%' OR raw_description LIKE '%po kolizji%')",
    "short ad": "length(raw_description) < 250",
    "long ad": "length(raw_description) > 4000",
    "market conflict today": "ai_conflict = 1",
    "plain": "origin_market IS NULL",
}


def pick_listings(conn, per_group: int):
    picked, seen = [], set()
    rng = random.Random(46)  # same ads on every run
    for group, where in GROUPS.items():
        rows = conn.execute(f"""
            SELECT id, source, source_url, raw_title, raw_description, make, model, location_city,
                   origin_market, ai_suggested_market, ai_summary
            FROM pending_listings
            WHERE status = 'approved' AND raw_description IS NOT NULL AND length(raw_description) > 30 AND {where}
            ORDER BY id
        """).fetchall()
        rows = [dict(r) for r in rows if r["id"] not in seen]
        for r in rng.sample(rows, min(per_group, len(rows))):
            seen.add(r["id"])
            picked.append({**r, "group": group})
    return picked


def run_model(model_name, listings):
    # First call loads the model, so it isn't counted in the timings
    enrich.analyze_with_bielik("BMW M3", "Sprzedam BMW M3, polski salon.", "BMW", "M3", model_name=model_name)
    results = {}
    for i, r in enumerate(listings, 1):
        started = time.time()
        try:
            out = enrich.analyze_with_bielik(r["raw_title"] or "", r["raw_description"], r["make"] or "", r["model"] or "",
                                             city=r["location_city"] or "", model_name=model_name)
            results[r["id"]] = {"data": {k: out.get(k) for k in FIELDS}, "seconds": round(time.time() - started, 1)}
        except Exception as e:
            results[r["id"]] = {"error": str(e)[:200], "seconds": round(time.time() - started, 1)}
        print(f"[{model_name}] {i}/{len(listings)} {results[r['id']]['seconds']}s", flush=True)
    return results


def render(listings, models, results):
    e = lambda v: html.escape("—" if v in (None, "", []) else (", ".join(v) if isinstance(v, list) else str(v)))
    rows = ["<tr><th>Model</th><th>Avg s/ad</th><th>Failed</th><th>Market set</th></tr>"]
    for m in models:
        res = results[m].values()
        ok = [r for r in res if "data" in r]
        avg = sum(r["seconds"] for r in ok) / len(ok) if ok else 0
        rows.append(f"<tr><td>{e(m)}</td><td>{avg:.1f}</td><td>{len(res) - len(ok)}</td>"
                    f"<td>{sum(1 for r in ok if r['data']['origin_market'])}/{len(res)}</td></tr>")
    cards = []
    for n, r in enumerate(listings, 1):
        cols = [f"<div class='col'><h4>Stored today</h4><p><b>Resolver market:</b> {e(r['origin_market'])}<br>"
                f"<b>AI market:</b> {e(r['ai_suggested_market'])}</p><p>{e(r['ai_summary'])}</p></div>"]
        for m in models:
            res = results[m][r["id"]]
            if "data" not in res:
                body = f"<p class='err'>Failed: {e(res['error'])}</p>"
            else:
                body = "".join(f"<p><b>{k}:</b> {e(res['data'][k])}</p>" for k in FIELDS)
            cols.append(f"<div class='col'><h4>{e(m)} <small>{res['seconds']}s</small></h4>{body}</div>")
        ad = e(enrich.clean_html(r["raw_description"]))
        cards.append(f"<section><h3>{n}. {e(r['raw_title'])} <small>{e(r['group'])} · {e(r['source'])} · "
                     f"<a href='{e(r['source_url'])}'>listing</a></small></h3><details><summary>Ad text</summary>"
                     f"<p>{ad}</p></details><div class='cols'>{''.join(cols)}</div></section>")
    style = """body{font:15px/1.45 system-ui;margin:0 auto;padding:16px;max-width:1400px;background:#fff;color:#1c1c1c}
    table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px 10px;text-align:left}
    section{border-top:2px solid #ddd;margin-top:24px;padding-top:8px}small{color:#666;font-weight:400}
    .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
    .col{background:#f5f5f5;padding:10px;border-radius:6px;overflow-wrap:anywhere}p{margin:4px 0}.err{color:#b00020}
    @media (prefers-color-scheme:dark){body{background:#181818;color:#eee}.col{background:#262626}small{color:#aaa}a{color:#8ab4f8}}"""
    return (f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>LLM comparison</title><style>{style}</style><h1>LLM comparison</h1>"
            f"<table>{''.join(rows)}</table>{''.join(cards)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="HTML report path; raw results go next to it as .json")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--per-group", type=int, default=5)
    args = parser.parse_args()

    conn = db.get_db()
    listings = pick_listings(conn, args.per_group)
    conn.close()
    print(f"{len(listings)} listings, models: {args.models}", flush=True)

    results = {m: run_model(m, listings) for m in args.models}
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(listings, args.models, results))
    with open(os.path.splitext(args.out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump({"listings": listings, "results": results}, f, ensure_ascii=False, indent=1)
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
