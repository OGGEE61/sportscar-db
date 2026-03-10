"""
db.py — SportsCar DB schema
============================
Design principles:
  - VIN is the permanent primary key for all vehicle identity
  - Every row records WHEN it was created (created_at, immutable) and HOW (source_method)
  - updated_at tracks field-level mutations; set by trigger automatically
  - Listings are observations: same ad seen N times = N rows, all timestamped
  - source_listing_id groups all observations of the same physical ad
  - Invalid/unknown VINs get placeholder format "UNVERIFIED-<SOURCE>-<ID>"
    and are corrected via resolve_placeholder() which logs the full chain
  - schema_migrations table allows safe future schema changes
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "sportscar_market.db")

# Canonical source_method values (used in every table):
#   'manual'          — entered by hand via web UI
#   'scraper-otomoto' — OtoMoto scraper
#   'scraper-olx'     — OLX scraper
#   'api'             — /api/ingest endpoint
#   'import'          — bulk CSV/JSON import


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── vehicles ──────────────────────────────────────────────────────────────
    c.execute("""
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
        vin_status          TEXT NOT NULL DEFAULT 'unverified',
            -- 'placeholder' | 'unverified' | 'verified'
        vin_verified_at     TEXT,
        vin_verified_by     TEXT,
        notes               TEXT,
        source_method       TEXT NOT NULL DEFAULT 'manual',
        created_at          TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    # ── listing_observations ───────────────────────────────────────────────────
    # Each row = one point-in-time observation of a listing.
    # Same ad seen across 3 weeks = 3 rows, linked by source_listing_id.
    c.execute("""
    CREATE TABLE IF NOT EXISTS listing_observations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        vin                 TEXT NOT NULL REFERENCES vehicles(vin) ON DELETE CASCADE,
        -- ad identity
        source              TEXT NOT NULL,
        source_listing_id   TEXT,
        source_url          TEXT,
        -- observed values at this moment
        title               TEXT,
        price_pln           REAL,
        price_eur           REAL,
        mileage_km          INTEGER,
        location_city       TEXT,
        location_region     TEXT,
        seller_type         TEXT,
        seller_name         TEXT,
        seller_id           TEXT,
        -- temporal markers
        first_seen_at       TEXT,
        observed_at         TEXT NOT NULL DEFAULT (datetime('now')),
        last_seen_at        TEXT,
        removed_at          TEXT,
        -- audit (created_at is immutable — never updated after insert)
        source_method       TEXT NOT NULL DEFAULT 'manual',
        notes               TEXT,
        created_at          TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    c.execute("""CREATE INDEX IF NOT EXISTS idx_obs_source_listing
        ON listing_observations(source, source_listing_id)
        WHERE source_listing_id IS NOT NULL""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_obs_vin        ON listing_observations(vin)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_obs_observed   ON listing_observations(observed_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_obs_price      ON listing_observations(price_pln) WHERE price_pln IS NOT NULL")

    # ── vin_correction_log ────────────────────────────────────────────────────
    c.execute("""
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
    c.execute("""
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_cond_vin ON condition_reports(vin)")

    # ── tags ──────────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        vin           TEXT NOT NULL REFERENCES vehicles(vin) ON DELETE CASCADE,
        tag           TEXT NOT NULL,
        source_method TEXT NOT NULL DEFAULT 'manual',
        created_at    TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(vin, tag)
    )""")

    # ── schema_migrations ─────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version    INTEGER PRIMARY KEY,
        name       TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(1,'initial_schema')")

    # ── Trigger: auto-update vehicles.updated_at ──────────────────────────────
    c.execute("DROP TRIGGER IF EXISTS trg_vehicles_updated")
    c.execute("""
    CREATE TRIGGER trg_vehicles_updated
    AFTER UPDATE ON vehicles
    BEGIN
        UPDATE vehicles SET updated_at = datetime('now') WHERE vin = NEW.vin;
    END""")

    conn.commit()
    conn.close()
    print("OK  Database initialised:", DB_PATH)


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
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM vehicles WHERE vin=?", (old_vin,)).fetchone()
        if not row:
            raise ValueError(f"VIN not found: {old_vin}")
        conn.execute("""
            INSERT OR IGNORE INTO vehicles
              (vin,make,model,variant,year,body_type,engine_cc,engine_cyl,power_hp,
               drivetrain,transmission,color_ext,color_int,
               vin_status,notes,source_method,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'unverified',?,?,?)
        """, (new_vin, row["make"], row["model"], row["variant"], row["year"],
              row["body_type"], row["engine_cc"], row["engine_cyl"], row["power_hp"],
              row["drivetrain"], row["transmission"], row["color_ext"], row["color_int"],
              row["notes"], source_method, row["created_at"]))
        for tbl in ("listing_observations", "condition_reports", "tags"):
            conn.execute(f"UPDATE {tbl} SET vin=? WHERE vin=?", (new_vin, old_vin))
        conn.execute("DELETE FROM vehicles WHERE vin=?", (old_vin,))
        conn.execute("""
            INSERT INTO vin_correction_log(old_vin,new_vin,reason,corrected_by,source_method)
            VALUES(?,?,?,?,?)
        """, (old_vin, new_vin, reason, corrected_by, source_method))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
