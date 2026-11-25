"""Copy the production D1 database into a local SQLite file, for audits and analysis.

Production D1 is on the free plan: 5 million rows read a day, after which every read fails until
midnight UTC and the app returns errors. Audits, page checks and exploratory SQL therefore run on
this copy, not on production. The copy reads each row once (pages by rowid, no OFFSET), so a full
export costs about as many reads as the database has rows (tens of thousands, ~1% of the day).

Usage: DB_BACKEND=d1 python scripts/maintenance/export_d1.py [OUT_FILE]   (default: local_copy.db)
Then:  DB_BACKEND=sqlite DB_PATH=local_copy.db python ...   (or point db.DB_PATH at it)
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
import db  # noqa: E402

PAGE = 500


def export(out_file: str) -> dict:
    src = db.get_db()
    if os.path.exists(out_file):
        os.remove(out_file)
    dst = sqlite3.connect(out_file)
    objects = src.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                          "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' "
                          "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END").fetchall()
    counts = {}
    for obj in objects:
        if obj["type"] != "table":
            continue
        table = obj["name"]
        dst.execute(obj["sql"])
        last, n = 0, 0
        while True:
            rows = src.execute(f'SELECT rowid AS _rowid_, * FROM "{table}" WHERE rowid > ? ORDER BY rowid LIMIT {PAGE}',
                               (last,)).fetchall()
            if not rows:
                break
            cols = [k for k in rows[0].keys() if k != "_rowid_"]
            dst.executemany(f'INSERT INTO "{table}" (rowid, {", ".join(chr(34) + c + chr(34) for c in cols)}) '
                            f'VALUES ({", ".join("?" * (len(cols) + 1))})',
                            [[r["_rowid_"]] + [r[c] for c in cols] for r in rows])
            last, n = rows[-1]["_rowid_"], n + len(rows)
        counts[table] = n
    for obj in objects:
        if obj["type"] in ("index", "trigger", "view"):
            try:
                dst.execute(obj["sql"])
            except sqlite3.Error as e:
                print(f"  {obj['type']} {obj['name']} skipped: {e}")
    dst.commit()
    dst.close()
    return counts


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "local_copy.db")
    db.ROWS_READ.reset()
    counts = export(out)
    print(f"Kopia zapisana: {out}")
    for t, n in counts.items():
        print(f"  {t}: {n} wierszy")
    print(f"Odczytano z D1: {db.ROWS_READ.count} wierszy")
