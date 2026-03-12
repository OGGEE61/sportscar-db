-- schema.sql
-- SportsCar DB — full DDL for Cloudflare D1 (and local SQLite)
--
-- Push to D1:
--   wrangler d1 execute sportscar-db --file=schema.sql --remote
--
-- Tables are listed in dependency order (parent before child).

-- ── vehicles ──────────────────────────────────────────────────────────────
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
    vin_verified_at     TEXT,
    vin_verified_by     TEXT,
    notes               TEXT,
    source_method       TEXT NOT NULL DEFAULT 'manual',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── listing_observations ──────────────────────────────────────────────────
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
);

CREATE INDEX IF NOT EXISTS idx_obs_source_listing
    ON listing_observations(source, source_listing_id)
    WHERE source_listing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_obs_vin      ON listing_observations(vin);
CREATE INDEX IF NOT EXISTS idx_obs_observed ON listing_observations(observed_at);
CREATE INDEX IF NOT EXISTS idx_obs_price    ON listing_observations(price_pln)
    WHERE price_pln IS NOT NULL;

-- ── vin_correction_log ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vin_correction_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    old_vin         TEXT NOT NULL,
    new_vin         TEXT NOT NULL,
    reason          TEXT,
    corrected_by    TEXT,
    source_method   TEXT NOT NULL DEFAULT 'manual',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── condition_reports ─────────────────────────────────────────────────────
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
);

CREATE INDEX IF NOT EXISTS idx_cond_vin ON condition_reports(vin);

-- ── tags ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tags (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vin           TEXT NOT NULL REFERENCES vehicles(vin) ON DELETE CASCADE,
    tag           TEXT NOT NULL,
    source_method TEXT NOT NULL DEFAULT 'manual',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(vin, tag)
);

-- ── schema_migrations ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── pending_listings ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pending_listings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL DEFAULT 'olx',
    source_listing_id   TEXT,
    source_url          TEXT,
    scraped_at          TEXT NOT NULL DEFAULT (datetime('now')),
    status              TEXT NOT NULL DEFAULT 'pending',
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
    doors               INTEGER,
    price_pln           REAL,
    price_eur           REAL,
    mileage_km          INTEGER,
    location_city       TEXT,
    location_region     TEXT,
    seller_type         TEXT,
    seller_name         TEXT,
    vin                 TEXT,
    vin_confidence      TEXT DEFAULT 'none',
    is_listing_active   INTEGER NOT NULL DEFAULT 1,
    review_notes        TEXT,
    reviewed_at         TEXT,
    UNIQUE(source, source_listing_id)
);

CREATE INDEX IF NOT EXISTS idx_pending_status  ON pending_listings(status);
CREATE INDEX IF NOT EXISTS idx_pending_scraped ON pending_listings(scraped_at);

-- ── Trigger: auto-update vehicles.updated_at ──────────────────────────────
CREATE TRIGGER IF NOT EXISTS trg_vehicles_updated
AFTER UPDATE ON vehicles
BEGIN
    UPDATE vehicles SET updated_at = datetime('now') WHERE vin = NEW.vin;
END;
