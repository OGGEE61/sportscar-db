"""
db.py — SportsCar DB schema + database backend abstraction
===========================================================
Supports two backends, selected via DB_BACKEND env var:
  DB_BACKEND=sqlite  (default) → local SQLite file (dev / single-machine)
  DB_BACKEND=d1                → Cloudflare D1 via REST API (production)

D1 is SQLite-compatible; all SQL is identical between backends.

Canonical source_method values (used in every table):
  'manual'          — entered by hand via web UI
  'scraper-otomoto' — OtoMoto scraper
  'scraper-olx'     — OLX scraper
  'api'             — /api/ingest endpoint
  'import'          — bulk CSV/JSON import
"""

import sqlite3
import os
import time
import requests as _http

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PATH = os.path.join(os.path.dirname(__file__), "sportscar_market.db")

# Shared keep-alive session: avoids a new TLS handshake for every D1 query
_D1_SESSION = _http.Session()


# ─────────────────────────────────────────────────────────────────────────────
# D1 Backend — row / cursor / connection wrappers
# ─────────────────────────────────────────────────────────────────────────────

class D1Row:
    """
    Row returned by D1 queries. Interface matches sqlite3.Row:
      r["column"]  — access by column name
      r[0]         — access by integer index
      r.keys()     — column names (enables dict(r) via Python mapping protocol)
      iter(r)      — yields values   (enables dict(list_of_rows) for 2-col queries)
    """

    def __init__(self, data: dict):
        self._data = data
        self._keys_list = list(data.keys())
        self._vals_list = list(data.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals_list[key]
        return self._data[key]

    def __iter__(self):
        # Yield values (not keys) — same as sqlite3.Row — so that
        # dict(list_of_2col_rows) works as {val0: val1, ...}.
        return iter(self._vals_list)

    def __len__(self):
        return len(self._data)

    def keys(self):
        # Presence of keys() makes Python's dict() use the mapping protocol:
        # dict(row) → {k: row[k] for k in row.keys()} = {col_name: value}
        return self._keys_list



class D1Cursor:
    """Mimics the sqlite3.Cursor interface for D1 query results."""

    def __init__(self, results: list, lastrowid=None, rowcount=-1):
        self._results = results or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        if self._results:
            row = self._results[0]
            return D1Row(row) if isinstance(row, dict) else row
        return None

    def fetchall(self):
        return [D1Row(r) if isinstance(r, dict) else r for r in self._results]

    def __iter__(self):
        return iter(self.fetchall())


class D1Backend:
    """
    Cloudflare D1 REST API backend.
    Mimics the sqlite3.Connection interface used by this app:
      execute(sql, params) → D1Cursor
      commit()             → no-op (D1 auto-commits each statement)
      close()              → no-op (stateless HTTP)

    Retry logic: 3 attempts with exponential backoff (1 s, 2 s) as recommended
    by the Cloudflare D1 docs for write queries.
    """

    _API_URL = (
        "https://api.cloudflare.com/client/v4/accounts/{account_id}"
        "/d1/database/{db_id}/query"
    )

    def __init__(self):
        self._account_id = os.environ["CF_ACCOUNT_ID"]
        self._db_id = os.environ["CF_D1_DATABASE_ID"]
        self._token = os.environ["CF_API_TOKEN"]
        self._url = self._API_URL.format(
            account_id=self._account_id, db_id=self._db_id
        )
        self._last_row_id = None

    def execute(self, sql: str, params=None) -> D1Cursor:
        sql = sql.strip()

        # Intercept SELECT last_insert_rowid() — return the value cached from
        # the most recent INSERT, matching SQLite connection-level behaviour.
        if sql.upper().startswith("SELECT LAST_INSERT_ROWID()"):
            return D1Cursor(
                [{"last_insert_rowid()": self._last_row_id}],
                lastrowid=self._last_row_id,
            )

        payload: dict = {"sql": sql}
        if params:
            payload["params"] = list(params)

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = _D1_SESSION.post(
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                if not resp.ok:
                    raise RuntimeError(f"D1 API returned {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                data = resp.json()

                if not data.get("success"):
                    raise RuntimeError(f"D1 error: {data.get('errors')}")

                stmt_result = data["result"][0]
                if not stmt_result.get("success"):
                    raise RuntimeError(f"D1 statement failed: {stmt_result}")

                results = stmt_result.get("results") or []
                meta = stmt_result.get("meta", {})
                last_row_id = meta.get("last_row_id")
                changes = meta.get("changes", -1)
                if last_row_id:
                    self._last_row_id = last_row_id

                return D1Cursor(results, lastrowid=last_row_id, rowcount=changes)

            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1 s then 2 s before retries

        raise RuntimeError(
            f"D1 query failed after 3 attempts: {last_exc}"
        ) from last_exc

    def commit(self):
        """No-op: D1 auto-commits every statement."""

    def close(self):
        """No-op: D1 is stateless HTTP, nothing to close."""


# ─────────────────────────────────────────────────────────────────────────────
# Backend factory
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    """Return a local SQLite connection (WAL mode, FK enforced)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    """
    Return the configured database backend.

    Set DB_BACKEND=d1 in your environment to use Cloudflare D1.
    Defaults to local SQLite for development.
    """
    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    if backend == "d1":
        return D1Backend()
    return get_conn()


# ─────────────────────────────────────────────────────────────────────────────
# Schema init / migrations
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    db = get_db()

    # ── vehicles ──────────────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        vin                 TEXT PRIMARY KEY,
        make                TEXT NOT NULL,
        model               TEXT NOT NULL,
        variant             TEXT,
        year                INTEGER NOT NULL,
        body_type           TEXT,
        engine_cc           INTEGER,
        engine_cyl          INTEGER,
        power_hp            INTEGER,
        drivetrain          TEXT,
        transmission        TEXT,
        color_ext           TEXT,
        color_int           TEXT,
        equipment           TEXT,
        registration_plate  TEXT,
        first_registration_date TEXT,
        vin_status          TEXT NOT NULL DEFAULT 'unverified',
            -- 'placeholder' | 'unverified' | 'verified'
        vin_verified_at     TEXT,
        vin_verified_by     TEXT,
        notes               TEXT,
        origin_market       TEXT,
        source_method       TEXT NOT NULL DEFAULT 'manual',
        created_at          TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    # ── listing_observations ───────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS listing_observations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        vin                 TEXT NOT NULL REFERENCES vehicles(vin) ON DELETE CASCADE,
        source              TEXT NOT NULL,
        source_listing_id   TEXT,
        source_url          TEXT,
        title               TEXT,
        price_pln           REAL,
        price_eur           REAL,
        mileage_km          INTEGER,
        location_city       TEXT,
        location_region     TEXT,
        seller_type         TEXT,
        seller_name         TEXT,
        seller_id           TEXT,
        first_seen_at       TEXT,
        observed_at         TEXT NOT NULL DEFAULT (datetime('now')),
        last_seen_at        TEXT,
        removed_at          TEXT,
        source_method       TEXT NOT NULL DEFAULT 'manual',
        notes               TEXT,
        created_at          TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    db.execute("""CREATE INDEX IF NOT EXISTS idx_obs_source_listing
        ON listing_observations(source, source_listing_id)
        WHERE source_listing_id IS NOT NULL""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_obs_vin        ON listing_observations(vin)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_obs_observed   ON listing_observations(observed_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_obs_price      ON listing_observations(price_pln) WHERE price_pln IS NOT NULL")

    # ── vin_correction_log ────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS vin_correction_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        old_vin         TEXT NOT NULL,
        new_vin         TEXT NOT NULL,
        reason          TEXT,
        corrected_by    TEXT,
        source_method   TEXT NOT NULL DEFAULT 'manual',
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    # ── condition_reports ─────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS condition_reports (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        vin             TEXT NOT NULL REFERENCES vehicles(vin) ON DELETE CASCADE,
        report_date     TEXT NOT NULL,
        mileage_km      INTEGER,
        accident_free   INTEGER,
        service_history TEXT,
        condition_score INTEGER,
        inspection_by   TEXT,
        notes           TEXT,
        source_method   TEXT NOT NULL DEFAULT 'manual',
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cond_vin ON condition_reports(vin)")

    # ── tags ──────────────────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        vin           TEXT NOT NULL REFERENCES vehicles(vin) ON DELETE CASCADE,
        tag           TEXT NOT NULL,
        source_method TEXT NOT NULL DEFAULT 'manual',
        created_at    TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(vin, tag)
    )""")

    # ── scraper_logs ──────────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS scraper_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date        TEXT NOT NULL DEFAULT (datetime('now')),
        status          TEXT NOT NULL,
        message         TEXT,
        processed_count INTEGER DEFAULT 0
    )""")

    # ── schema_migrations ─────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version    INTEGER PRIMARY KEY,
        name       TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(1,'initial_schema')")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(2,'pending_listings')")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(3,'pending_is_listing_active')")

    # ── pending_listings ───────────────────────────────────────────────────────
    db.execute("""
    CREATE TABLE IF NOT EXISTS pending_listings (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        source              TEXT NOT NULL DEFAULT 'olx',
        source_listing_id   TEXT,
        source_url          TEXT,
        scraped_at          TEXT NOT NULL DEFAULT (datetime('now')),
        status              TEXT NOT NULL DEFAULT 'pending',
            -- 'pending' | 'approved' | 'rejected'
        raw_title           TEXT,
        raw_description     TEXT,
        photos              TEXT,
        make                TEXT,
        model               TEXT,
        variant             TEXT,
        year                INTEGER,
        body_type           TEXT,
        engine_cc           INTEGER,
        power_hp            INTEGER,
        fuel_type           TEXT,
        drivetrain          TEXT,
        transmission        TEXT,
        color_ext           TEXT,
        color_int           TEXT,
        equipment           TEXT,
        doors               INTEGER,
        price_pln           REAL,
        price_eur           REAL,
        mileage_km          INTEGER,
        location_city       TEXT,
        location_region     TEXT,
        seller_type         TEXT,
        seller_name         TEXT,
        vin                 TEXT,
        origin_market       TEXT,
        vin_confidence      TEXT DEFAULT 'none',
            -- 'found_in_schema' | 'found_in_description' | 'none'
        is_listing_active   INTEGER NOT NULL DEFAULT 1,
        review_notes        TEXT,
        reviewed_at         TEXT,
        UNIQUE(source, source_listing_id)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_listings(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pending_scraped ON pending_listings(scraped_at)")

    # Migration v3: add is_listing_active if upgrading from v2 (table already exists without it)
    existing_cols = [r[1] for r in db.execute("PRAGMA table_info(pending_listings)").fetchall()]
    if "is_listing_active" not in existing_cols:
        db.execute("ALTER TABLE pending_listings ADD COLUMN is_listing_active INTEGER NOT NULL DEFAULT 1")

    # Migration v4: local_photo — cached compressed photo path for pending_listings
    if "local_photo" not in existing_cols:
        db.execute("ALTER TABLE pending_listings ADD COLUMN local_photo TEXT")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(4,'local_photo')")

    # Migration v5: photo column on vehicles — set when a listing is approved
    v_cols = [r[1] for r in db.execute("PRAGMA table_info(vehicles)").fetchall()]
    if "photo" not in v_cols:
        db.execute("ALTER TABLE vehicles ADD COLUMN photo TEXT")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(5,'vehicle_photo')")

    # Migration v6: registration_plate and first_registration_date
    if "registration_plate" not in v_cols:
        db.execute("ALTER TABLE vehicles ADD COLUMN registration_plate TEXT")
    if "first_registration_date" not in v_cols:
        db.execute("ALTER TABLE vehicles ADD COLUMN first_registration_date TEXT")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(6,'vehicle_registration')")

    # Migration v7: origin_market
    if "origin_market" not in v_cols:
        db.execute("ALTER TABLE vehicles ADD COLUMN origin_market TEXT")
    if "origin_market" not in existing_cols:
        db.execute("ALTER TABLE pending_listings ADD COLUMN origin_market TEXT")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(7,'origin_market')")

    # Migration v8: color_int and equipment
    if "equipment" not in v_cols:
        db.execute("ALTER TABLE vehicles ADD COLUMN equipment TEXT")
    if "color_int" not in existing_cols:
        db.execute("ALTER TABLE pending_listings ADD COLUMN color_int TEXT")
    if "equipment" not in existing_cols:
        db.execute("ALTER TABLE pending_listings ADD COLUMN equipment TEXT")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(8,'color_int_equipment')")

    # Migration v9: plate_review_queue & cepik_reports
    db.execute("""
    CREATE TABLE IF NOT EXISTS plate_review_queue (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id          TEXT,
        vin                 TEXT,
        source_url          TEXT,
        photo_url           TEXT,
        crop_path           TEXT,
        detected_plate      TEXT,
        confidence          REAL,
        status              TEXT NOT NULL DEFAULT 'pending',
        reviewed_plate      TEXT,
        reviewed_at         TEXT,
        created_at          TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_plate_queue_status ON plate_review_queue(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_plate_queue_vin ON plate_review_queue(vin)")

    db.execute("""
    CREATE TABLE IF NOT EXISTS cepik_reports (
        vin                     TEXT PRIMARY KEY,
        registration_plate      TEXT,
        first_registration_date TEXT,
        make                    TEXT,
        model                   TEXT,
        type                    TEXT,
        subtype                 TEXT,
        registration_status     TEXT,
        tech_inspection_status  TEXT,
        tech_inspection_until   TEXT,
        has_current_oc          INTEGER,
        insurance_expiry_date   TEXT,
        is_stolen               INTEGER DEFAULT 0,
        total_owners            INTEGER,
        last_odometer_km        INTEGER,
        last_odometer_date      TEXT,
        odometer_history_json   TEXT,
        events_json             TEXT,
        odometer_rollback       INTEGER DEFAULT 0,
        rollback_diff_km        INTEGER DEFAULT 0,
        fetched_at              TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(vin) REFERENCES vehicles(vin)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cepik_reports_plate ON cepik_reports(registration_plate)")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(9,'plate_queue_and_cepik')")

    # Migration v10: columns the app/scripts use that were previously only added
    # by hand on production (fresh databases crashed on /logs, plates, AI views)
    missing_cols = {
        "scraper_logs": [
            ("is_read", "INTEGER NOT NULL DEFAULT 0"),
            ("list_url", "TEXT"),
            ("found_count", "INTEGER DEFAULT 0"),
            ("new_count", "INTEGER DEFAULT 0"),
            ("dup_count", "INTEGER DEFAULT 0"),
            ("rej_count", "INTEGER DEFAULT 0"),
        ],
        "listing_observations": [
            ("registration_plate", "TEXT"),
        ],
        "pending_listings": [
            ("registration_plate", "TEXT"),
            ("first_registration_date", "TEXT"),
            ("ai_summary", "TEXT"),
            ("ai_suggested_market", "TEXT"),
            ("ai_conflict", "INTEGER"),
            ("ai_reasoning", "TEXT"),
            ("ai_equipment", "TEXT"),
            ("ai_interior_color", "TEXT"),
            ("ai_processed_at", "TEXT"),
        ],
        "vehicles": [
            ("ai_summary", "TEXT"),
        ],
    }
    for table, cols in missing_cols.items():
        have = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, decl in cols:
            if col not in have:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    db.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(10,'backfill_missing_columns')")

    # ── Trigger: auto-update vehicles.updated_at ──────────────────────────────
    db.execute("DROP TRIGGER IF EXISTS trg_vehicles_updated")
    db.execute("""
    CREATE TRIGGER trg_vehicles_updated
    AFTER UPDATE ON vehicles
    BEGIN
        UPDATE vehicles SET updated_at = datetime('now') WHERE vin = NEW.vin;
    END""")

    db.commit()
    db.close()
    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    print(f"OK  Database initialised (backend: {backend})")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_placeholder_vin(source: str, source_listing_id: str) -> str:
    """Deterministic placeholder for listings whose VIN is unknown/invalid."""
    slug = f"{source.upper()}-{source_listing_id}"[:28]
    return f"UNVERIFIED-{slug}"


def resolve_placeholder(old_vin: str, new_vin: str,
                         reason: str = "placeholder resolved",
                         corrected_by: str = "manual",
                         source_method: str = "manual"):
    """
    Re-key all data from a placeholder VIN to a real/corrected VIN.
    FK cascade handles child tables; the correction is fully logged.
    """
    db = get_db()
    try:
        row = db.execute("SELECT * FROM vehicles WHERE vin=?", (old_vin,)).fetchone()
        if not row:
            raise ValueError(f"VIN not found: {old_vin}")
        # Copy every column except the identity/status ones, so nothing set on
        # the placeholder (photo, plate, equipment, AI summary, ...) is lost.
        skip = {"vin", "vin_status", "vin_verified_at", "vin_verified_by", "source_method", "updated_at"}
        cols = [k for k in row.keys() if k not in skip]
        db.execute(f"""
            INSERT OR IGNORE INTO vehicles (vin, vin_status, source_method, {', '.join(cols)})
            VALUES (?, 'unverified', ?, {', '.join('?' * len(cols))})
        """, (new_vin, source_method, *[row[c] for c in cols]))
        # If the real VIN already existed, fill its gaps from the placeholder
        fill = [c for c in cols if c not in ("created_at",)]
        if fill:
            db.execute(f"""
                UPDATE vehicles SET {', '.join(f'{c} = COALESCE({c}, ?)' for c in fill)}
                WHERE vin = ?
            """, (*[row[c] for c in fill], new_vin))
        for tbl in ("listing_observations", "condition_reports", "tags", "plate_review_queue"):
            if tbl == "tags":
                # tags has UNIQUE(vin, tag): drop duplicates the real VIN already has
                db.execute("""
                    DELETE FROM tags WHERE vin=? AND tag IN (SELECT tag FROM tags WHERE vin=?)
                """, (old_vin, new_vin))
            db.execute(f"UPDATE {tbl} SET vin=? WHERE vin=?", (new_vin, old_vin))
        db.execute("UPDATE pending_listings SET vin=? WHERE vin=?", (new_vin, old_vin))
        db.execute("""
            UPDATE cepik_reports SET vin=? WHERE vin=?
              AND NOT EXISTS (SELECT 1 FROM cepik_reports WHERE vin=?)
        """, (new_vin, old_vin, new_vin))
        db.execute("DELETE FROM cepik_reports WHERE vin=?", (old_vin,))
        db.execute("DELETE FROM vehicles WHERE vin=?", (old_vin,))
        db.execute("""
            INSERT INTO vin_correction_log(old_vin,new_vin,reason,corrected_by,source_method)
            VALUES(?,?,?,?,?)
        """, (old_vin, new_vin, reason, corrected_by, source_method))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()